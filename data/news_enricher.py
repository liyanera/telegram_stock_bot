"""
News enrichment pipeline:
1. Fetch last 3 days of news for a ticker
2. Use Claude Haiku to summarize + sentiment score
3. Store enriched summary in ChromaDB for future RAG
4. Persist themes to MySQL + knowledge/news_themes/TICKER.md
"""
import json
import logging
from datetime import datetime
from pathlib import Path
import anthropic
import config
from data.news import get_stock_news
from memory.vector_memory import add_knowledge

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def enrich_and_store_news(ticker: str, company_name: str = "") -> dict:
    """
    Fetch news, summarize with sentiment, store in ChromaDB.
    Returns the enriched summary dict.
    """
    ticker = ticker.upper()
    articles = get_stock_news(ticker, company_name, max_articles=15)
    valid = [a for a in articles if a.get("title") and not a.get("error")]

    if not valid:
        return {"ticker": ticker, "summary": "No recent news found.", "sentiment": "neutral", "score": 0}

    headlines = "\n".join(
        f"- [{a['source']}] {a['title']} ({a.get('published_at','')[:10]})"
        for a in valid
    )

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Analyze these news headlines for {ticker} from the last 3 days.

{headlines}

Return ONLY valid JSON:
{{
  "sentiment": "bullish|bearish|neutral",
  "score": <float -1.0 to 1.0>,
  "key_themes": ["theme1", "theme2"],
  "summary": "2-3 sentence synthesis of what's happening and why it matters for the stock",
  "catalysts": ["positive catalyst or risk 1", "catalyst 2"]
}}"""
            }]
        )
        import re
        raw = response.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group()) if match else {}
    except Exception as e:
        logger.warning(f"News enrichment Haiku call failed for {ticker}: {e}")
        result = {}

    enriched = {
        "ticker": ticker,
        "sentiment": result.get("sentiment", "neutral"),
        "score": result.get("score", 0.0),
        "key_themes": result.get("key_themes", []),
        "summary": result.get("summary", ""),
        "catalysts": result.get("catalysts", []),
        "article_count": len(valid),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    # Store in ChromaDB for RAG — future queries about this stock get this context
    if enriched["summary"]:
        doc_id = f"news-{ticker}-{enriched['date']}"
        sentiment_label = enriched["sentiment"].upper()
        cred = 0.6 if abs(enriched["score"]) > 0.3 else 0.5
        add_knowledge(
            doc_id,
            f"[NEWS SENTIMENT: {sentiment_label}] {ticker} as of {enriched['date']}:\n"
            f"{enriched['summary']}\n"
            f"Key themes: {', '.join(enriched['key_themes'])}\n"
            f"Catalysts/Risks: {'; '.join(enriched['catalysts'])}",
            metadata={
                "ticker": ticker,
                "type": "news_sentiment",
                "sentiment": enriched["sentiment"],
                "score": enriched["score"],
                "credibility": cred,
                "date": enriched["date"],
            },
        )
        logger.info(f"News enriched and stored for {ticker}: {sentiment_label} (score={enriched['score']:.2f})")

    # Persist themes to MySQL + knowledge file
    if enriched["key_themes"] or enriched["catalysts"]:
        try:
            from memory.mysql_memory import save_news_theme
            save_news_theme(
                ticker=ticker,
                date=enriched["date"],
                sentiment=enriched["sentiment"],
                score=enriched["score"],
                themes=enriched["key_themes"],
                catalysts=enriched["catalysts"],
            )
            _save_news_theme_knowledge(ticker, enriched)
        except Exception as e:
            logger.debug(f"News theme persist failed (non-fatal): {e}")

    return enriched


def _save_news_theme_knowledge(ticker: str, enriched: dict):
    """Append this date's news theme to knowledge/news_themes/TICKER.md."""
    kb_dir = Path(__file__).parent.parent / "knowledge" / "news_themes"
    kb_dir.mkdir(parents=True, exist_ok=True)
    path = kb_dir / f"{ticker}.md"
    sentiment_icon = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(
        enriched["sentiment"], "➡️"
    )
    lines = [
        f"\n## {enriched['date']} {sentiment_icon} {enriched['sentiment'].upper()} "
        f"(score: {enriched['score']:+.2f})",
        f"**Summary**: {enriched['summary']}",
    ]
    if enriched["key_themes"]:
        lines.append(f"**Themes**: {', '.join(enriched['key_themes'])}")
    if enriched["catalysts"]:
        lines.append(f"**Catalysts/Risks**: {'; '.join(enriched['catalysts'])}")
    with open(path, "a") as f:
        if not path.exists() or path.stat().st_size == 0:
            f.write(f"# News Themes — {ticker}\n")
        f.write("\n".join(lines) + "\n")
