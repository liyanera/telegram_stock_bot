"""
Weekly Price Monitor — runs every Monday.
1. For every watchlisted ticker, check if price moved >10% since last snapshot
2. If yes: ask Claude whether the move aligns with stored theses
3. Update credibility in MySQL + ChromaDB
4. Save new price snapshot

Run: python scripts/weekly_monitor.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf
import anthropic
import config
from memory import mysql_memory
from memory.vector_memory import update_credibility, add_knowledge
from data.news import get_stock_news

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
THRESHOLD = 10.0  # % change to trigger analysis


def get_current_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        return round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else None
    except Exception:
        return None


def assess_consistency(ticker: str, price_change_pct: float, theses: list, news: list) -> list[dict]:
    """
    Ask Claude: for each thesis, does this week's price movement align?
    Returns list of {thesis_id, consistent: bool, reason: str}
    """
    news_text = "\n".join(f"- {n.get('title','')}" for n in news if n.get("title"))
    theses_text = json.dumps([
        {"id": t["id"], "type": t["thesis_type"], "thesis": t["thesis"],
         "credibility": t["credibility"]}
        for t in theses
    ], indent=2)

    direction = "UP" if price_change_pct > 0 else "DOWN"
    prompt = f"""Stock: {ticker}
Price moved {direction} {abs(price_change_pct):.1f}% this week.

Recent news headlines:
{news_text or "No news available."}

Stored theses to evaluate:
{theses_text}

For each thesis, determine if this week's price movement is CONSISTENT or INCONSISTENT with the thesis.
- CONSISTENT: price moved in the direction the thesis predicted, AND the reason aligns with the news
- INCONSISTENT: price moved opposite to the thesis, OR the reason is clearly different from what drove the move

Return ONLY valid JSON array:
[{{"thesis_id": 1, "consistent": true, "reason": "one sentence explanation"}}]"""

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        import re
        raw = response.content[0].text.strip()
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(match.group()) if match else []
    except Exception as e:
        print(f"  Claude assessment failed: {e}")
        return []


def run_monitor():
    mysql_memory.init_db()
    tickers = mysql_memory.get_all_monitored_tickers()
    if not tickers:
        print("No tickers in watchlist.")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"Weekly Price Monitor — {date_str}")
    print(f"Monitoring {len(tickers)} tickers: {', '.join(tickers)}")
    print(f"{'='*60}\n")

    alerts = []

    for ticker in tickers:
        current_price = get_current_price(ticker)
        if not current_price:
            print(f"  {ticker}: could not fetch price, skipping")
            continue

        last = mysql_memory.get_last_snapshot(ticker)

        if not last:
            # First time: just save snapshot, no comparison
            mysql_memory.save_price_snapshot(ticker, current_price)
            print(f"  {ticker}: first snapshot saved @ ${current_price}")
            continue

        last_price = last["price"]
        change_pct = (current_price - last_price) / last_price * 100
        print(f"  {ticker}: ${last_price} → ${current_price} ({change_pct:+.1f}%)")

        if abs(change_pct) >= THRESHOLD:
            print(f"    ⚡ >10% move detected — analyzing thesis consistency...")
            alerts.append({"ticker": ticker, "change_pct": change_pct,
                           "last_price": last_price, "current_price": current_price})

            theses = mysql_memory.get_theses(ticker)
            if not theses:
                print(f"    No theses found for {ticker}, skipping assessment.")
            else:
                news = get_stock_news(ticker, max_articles=5)
                assessments = assess_consistency(ticker, change_pct, theses, news)

                for assessment in assessments:
                    thesis_id = assessment.get("thesis_id")
                    consistent = assessment.get("consistent", False)
                    reason = assessment.get("reason", "")

                    # Update MySQL credibility
                    new_cred = mysql_memory.update_thesis_credibility(thesis_id, consistent)

                    # Update ChromaDB credibility
                    thesis_row = next((t for t in theses if t["id"] == thesis_id), None)
                    if thesis_row and thesis_row.get("chroma_doc_id"):
                        update_credibility(thesis_row["chroma_doc_id"], new_cred or 0.5)

                    status = "✅ CONSISTENT" if consistent else "❌ INCONSISTENT"
                    print(f"    Thesis #{thesis_id}: {status} (credibility → {new_cred:.2f})")
                    print(f"      Reason: {reason}")

                # Save the assessment itself to knowledge base for future reference
                assessment_text = (
                    f"[PRICE ALERT {date_str}] {ticker} moved {change_pct:+.1f}%.\n"
                    + "\n".join(
                        f"Thesis #{a['thesis_id']} was {'CONFIRMED' if a['consistent'] else 'CONTRADICTED'}: {a['reason']}"
                        for a in assessments
                    )
                )
                add_knowledge(
                    f"alert-{ticker}-{date_str}",
                    assessment_text,
                    metadata={"ticker": ticker, "type": "price_alert",
                              "change_pct": change_pct, "date": date_str, "credibility": 0.6},
                )

        # Save new price snapshot
        mysql_memory.save_price_snapshot(ticker, current_price)

    print(f"\n{'='*60}")
    print(f"Summary: {len(alerts)} tickers with >10% moves:")
    for a in alerts:
        print(f"  {a['ticker']}: {a['change_pct']:+.1f}% (${a['last_price']} → ${a['current_price']})")

    if not alerts:
        print("  No significant moves this week.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_monitor()
