"""
Daily Pre-Market News Tracker
Runs at 13:00 UTC (30 min before US market open at 9:00 AM ET)

1. Enrich news for all watchlisted stocks → ChromaDB
2. Fetch and summarize macro events (Fed, CPI, rates, indices) → ChromaDB
"""
import json
import re
import logging
from datetime import datetime, timedelta

import httpx
import yfinance as yf
import anthropic
import config
from memory.mysql_memory import init_db, get_all_monitored_tickers
from memory.vector_memory import add_knowledge
from data.news_enricher import enrich_and_store_news

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Macro proxies: indices + sector ETFs
MACRO_TICKERS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000 Small Cap",
    "VIX": "Volatility Index",
    "TLT": "20Y Treasury Bond",
    "DXY": "US Dollar Index",
    "GLD": "Gold",
    "XLK": "Technology Sector",
    "XLF": "Financial Sector",
    "XLE": "Energy Sector",
}

# Macro news search terms (NewsAPI)
MACRO_KEYWORDS = [
    "Federal Reserve interest rate",
    "inflation CPI PPI",
    "US jobs report unemployment",
    "GDP economic growth",
    "S&P 500 stock market",
    "Treasury yield bond market",
]


# ── Stock watchlist news ──────────────────────────────────────────────────────

def run_watchlist_enrichment() -> list[dict]:
    tickers = get_all_monitored_tickers()
    if not tickers:
        logger.info("No watchlist tickers to enrich.")
        return []

    logger.info(f"Pre-market enrichment for {len(tickers)} watchlist stocks: {', '.join(tickers)}")
    results = []
    for ticker in tickers:
        try:
            enriched = enrich_and_store_news(ticker)
            results.append(enriched)
            sentiment = enriched.get("sentiment", "neutral")
            score = enriched.get("score", 0)
            logger.info(f"  {ticker}: {sentiment} (score={score:.2f})")
        except Exception as e:
            logger.warning(f"  {ticker}: enrichment failed — {e}")

    return results


# ── Macro market snapshot ─────────────────────────────────────────────────────

def _get_macro_price_snapshot() -> dict:
    """Get overnight price changes for key indices and assets."""
    snapshot = {}
    for ticker, name in MACRO_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev = hist["Close"].iloc[-2]
                curr = hist["Close"].iloc[-1]
                chg = (curr - prev) / prev * 100
                snapshot[ticker] = {
                    "name": name,
                    "price": round(curr, 2),
                    "change_pct": round(chg, 2),
                }
        except Exception:
            continue
    return snapshot


def _get_macro_news() -> list[dict]:
    """Fetch macro news via NewsAPI or fallback to yfinance index news."""
    articles = []
    from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    if config.NEWS_API_KEY:
        for query in MACRO_KEYWORDS[:3]:  # Limit to 3 queries to save API calls
            try:
                r = httpx.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "from": from_date,
                        "sortBy": "publishedAt",
                        "pageSize": 5,
                        "language": "en",
                        "apiKey": config.NEWS_API_KEY,
                    },
                    timeout=10,
                )
                for a in r.json().get("articles", []):
                    articles.append({
                        "title": a.get("title", ""),
                        "source": a.get("source", {}).get("name", ""),
                        "published_at": a.get("publishedAt", "")[:10],
                        "description": a.get("description", "") or "",
                    })
            except Exception:
                continue
    else:
        # Fallback: yfinance news for SPY and QQQ
        for ticker in ["SPY", "QQQ"]:
            try:
                news = yf.Ticker(ticker).news or []
                for n in news[:5]:
                    articles.append({
                        "title": n.get("title", ""),
                        "source": n.get("publisher", ""),
                        "published_at": "",
                        "description": "",
                    })
            except Exception:
                continue

    return articles[:20]


def run_macro_enrichment(price_snapshot: dict, news_articles: list) -> dict:
    """Summarize macro environment with Haiku and store in ChromaDB."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Build price summary string
    price_lines = []
    for ticker, data in price_snapshot.items():
        sign = "+" if data["change_pct"] >= 0 else ""
        price_lines.append(
            f"  {ticker} ({data['name']}): {data['price']} ({sign}{data['change_pct']}%)"
        )
    price_text = "\n".join(price_lines) if price_lines else "No price data available."

    # Build news headlines string
    headlines = "\n".join(
        f"- [{a['source']}] {a['title']}"
        for a in news_articles if a.get("title")
    ) or "No macro news available."

    prompt = f"""You are a macro analyst. Today is {date_str}, 30 minutes before US market open.

Overnight market moves:
{price_text}

Recent macro headlines:
{headlines}

Provide a concise pre-market macro briefing for a US growth stock investor.
Return ONLY valid JSON:
{{
  "market_tone": "risk-on|risk-off|neutral",
  "key_themes": ["theme1", "theme2", "theme3"],
  "summary": "3-4 sentence briefing covering overnight moves, key macro events, and what it means for growth stocks today",
  "watch_list": ["specific thing to watch during today's session 1", "thing 2"],
  "impact_on_growth_stocks": "bullish|bearish|neutral",
  "reason": "one sentence on why growth stocks specifically are affected"
}}"""

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        macro_data = json.loads(match.group()) if match else {}
    except Exception as e:
        logger.error(f"Macro Haiku call failed: {e}")
        macro_data = {}

    result = {
        "date": date_str,
        "market_tone": macro_data.get("market_tone", "neutral"),
        "key_themes": macro_data.get("key_themes", []),
        "summary": macro_data.get("summary", ""),
        "watch_list": macro_data.get("watch_list", []),
        "impact_on_growth_stocks": macro_data.get("impact_on_growth_stocks", "neutral"),
        "reason": macro_data.get("reason", ""),
        "price_snapshot": price_snapshot,
    }

    # Store in ChromaDB — injected into analysis when user asks macro questions
    if result["summary"]:
        tone = result["market_tone"].upper()
        themes = ", ".join(result["key_themes"])
        doc_text = (
            f"[PRE-MARKET MACRO BRIEFING {date_str} — {tone}]\n"
            f"{result['summary']}\n"
            f"Key themes: {themes}\n"
            f"Impact on growth stocks: {result['impact_on_growth_stocks']} — {result['reason']}\n"
            f"Watch today: {'; '.join(result['watch_list'])}\n\n"
            f"Overnight moves:\n" + "\n".join(
                f"  {t}: {d['change_pct']:+.1f}%"
                for t, d in price_snapshot.items()
            )
        )
        add_knowledge(
            f"macro-briefing-{date_str}",
            doc_text,
            metadata={
                "type": "macro_briefing",
                "market_tone": result["market_tone"],
                "date": date_str,
                "credibility": 0.7,  # Macro facts are more reliable than stock theses
            },
        )
        logger.info(f"Macro briefing stored: {tone} | themes: {themes}")

    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def run_daily_premarket():
    init_db()
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    logger.info(f"\n{'='*60}")
    logger.info(f"Daily Pre-Market Tracker — {date_str} (US open in ~30 min)")
    logger.info(f"{'='*60}")

    # 1. Enrich watchlist stocks
    stock_results = run_watchlist_enrichment()

    # 2. Macro snapshot + news
    logger.info("Fetching macro price snapshot and news...")
    price_snapshot = _get_macro_price_snapshot()
    macro_news = _get_macro_news()
    macro_result = run_macro_enrichment(price_snapshot, macro_news)

    # 3. Summary log
    logger.info(f"\nPre-Market Summary ({date_str}):")
    logger.info(f"  Market tone: {macro_result.get('market_tone','?').upper()}")
    logger.info(f"  Growth stock impact: {macro_result.get('impact_on_growth_stocks','?')}")
    logger.info(f"  Key themes: {', '.join(macro_result.get('key_themes', []))}")
    logger.info(f"  Stocks enriched: {len(stock_results)}")
    logger.info(f"  Macro briefing stored to ChromaDB ✓")
    logger.info(f"{'='*60}\n")

    return {"stocks": stock_results, "macro": macro_result}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/scripts", 1)[0])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_daily_premarket()
