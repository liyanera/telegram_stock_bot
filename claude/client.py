import json
import re
import logging
import anthropic
import config
from claude.tools import TOOLS
from claude.prompts import build_system_prompt, build_static_persona
from memory import redis_memory, mysql_memory
from memory.vector_memory import add_knowledge, search as knowledge_search
from data.stocks import get_stock_price, get_financials, get_technical_indicators
from data.news import get_stock_news
from data.universe import get_full_universe, screen_by_weekly_performance

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Regex pre-filter: only fire Haiku extraction if response mentions ticker-like patterns
_TICKER_PATTERN = re.compile(r'\b[A-Z]{2,5}\b')
_ANALYSIS_KEYWORDS = {
    "P/E", "revenue", "growth", "RSI", "MACD", "margin", "bullish", "bearish",
    "buy", "sell", "target", "catalyst", "thesis", "valuation", "FCF", "EPS"
}
_SKIP_WORDS = {
    "A", "AT", "BE", "BY", "GO", "HI", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "AI", "US", "OK", "TV", "CEO", "CFO", "COO", "IPO", "ETF", "GDP",
    "YOY", "QOQ", "TTM", "NTM", "FCF", "EPS", "SMA", "RSI", "PE",
}


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_stock_price":
            result = get_stock_price(tool_input["ticker"])

        elif tool_name == "get_financials":
            result = get_financials(tool_input["ticker"])

        elif tool_name == "get_technical_indicators":
            result = get_technical_indicators(
                tool_input["ticker"],
                tool_input.get("period", "3mo"),
            )

        elif tool_name == "get_stock_news":
            result = get_stock_news(
                tool_input["ticker"],
                tool_input.get("company_name", ""),
            )

        elif tool_name == "get_recommendations":
            thesis_type = tool_input.get("thesis_type", "bull")
            min_cred = float(tool_input.get("min_credibility", 0.0))
            limit = int(tool_input.get("limit", 10))
            rows = mysql_memory.get_all_theses_ranked(
                thesis_type=thesis_type,
                min_credibility=min_cred,
                limit=limit,
            )
            needs_discovery = (
                not rows or
                all(r.get("credibility", 0) < 0.5 for r in rows)
            )
            if needs_discovery:
                fresh = _discover_fresh_picks(n=5)
                if fresh:
                    result = fresh
                elif rows:
                    for r in rows:
                        r["note"] = "⚠️ Low credibility — treat as speculative"
                    result = rows
                else:
                    result = [{"message": "Discovery failed — please try again shortly."}]
            else:
                result = rows

        elif tool_name == "search_knowledge_base":
            chunks = knowledge_search(tool_input["query"])
            result = [c["text"] for c in chunks] if chunks else ["No relevant knowledge found."]

        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── On-demand discovery ───────────────────────────────────────────────────────

def _discover_fresh_picks(n: int = 5) -> list:
    """Full-market on-demand discovery via batch screening + Claude Haiku."""
    logger.info("Running on-demand discovery across full market universe...")
    from datetime import datetime

    universe = get_full_universe()
    logger.info(f"Universe size: {len(universe)} tickers")

    screened = screen_by_weekly_performance(universe, top_n=60, min_market_cap_b=2.0)
    if screened.empty:
        return []

    candidates = screened["ticker"].tolist()
    logger.info(f"Screened to {len(candidates)} candidates for deep analysis")

    snapshots = []
    for ticker in candidates:
        try:
            f = get_financials(ticker)
            p = get_stock_price(ticker)
            row = screened.loc[screened["ticker"] == ticker]
            snapshots.append({
                "ticker": ticker,
                "company": f.get("company_name", ticker),
                "sector": f.get("sector"),
                "price": p.get("price"),
                "weekly_return_pct": float(row["weekly_return_pct"].values[0]) if not row.empty else 0,
                "revenue_growth": f.get("revenue_growth") or 0,
                "gross_margin": f.get("gross_margin") or 0,
                "forward_pe": f.get("forward_pe"),
                "free_cash_flow": f.get("free_cash_flow"),
                "profit_margin": f.get("profit_margin") or 0,
                "analyst_target": f.get("analyst_target_price"),
                "recommendation": f.get("recommendation"),
            })
        except Exception:
            continue

    if not snapshots:
        return []

    logger.info(f"Deep analysis ready for {len(snapshots)} stocks")

    prompt = f"""You are an elite US growth stock analyst. Today is {datetime.utcnow().strftime('%Y-%m-%d')}.
From the data below, identify the {n} most undervalued stocks with the best growth potential.
Prioritize: high revenue growth, strong margins, reasonable forward P/E, real FCF.

Universe data:
{json.dumps(snapshots, default=str)}

Return ONLY a JSON array of exactly {n} picks:
[{{"ticker":"AAPL","thesis_type":"bull","thesis":"1-2 sentence reason","key_metrics":"e.g. 33% growth, 17x fwd P/E"}}]"""

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return []
        picks = json.loads(match.group())
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return []

    date_str = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    saved = []
    for pick in picks:
        ticker = pick.get("ticker", "").upper()
        thesis = pick.get("thesis", "")
        thesis_type = pick.get("thesis_type", "bull")
        if not ticker or not thesis:
            continue
        chroma_id = f"thesis-{ticker}-discovery-{date_str}"
        thesis_id = mysql_memory.save_thesis(
            ticker=ticker, thesis=thesis, thesis_type=thesis_type,
            source="on_demand_discovery", chroma_doc_id=chroma_id,
        )
        add_knowledge(
            chroma_id,
            f"[{thesis_type.upper()} thesis for {ticker}] {thesis}",
            metadata={"ticker": ticker, "thesis_type": thesis_type,
                      "credibility": 0.5, "thesis_id": thesis_id, "type": "stock_thesis"},
        )
        saved.append({
            "ticker": ticker, "thesis_type": thesis_type, "thesis": thesis,
            "credibility": 0.5, "confirmed_count": 0, "contradicted_count": 0,
            "source": "on_demand_discovery", "key_metrics": pick.get("key_metrics", ""),
            "note": "freshly discovered — credibility starts at 0.5, improves with weekly monitoring",
        })
        logger.info(f"New pick discovered: {ticker}")

    return saved


# ── Post-response extraction (Haiku) ─────────────────────────────────────────

def _extract_analyses(user_message: str, assistant_response: str) -> list:
    """
    Optimization 1: fast pre-filter guards before firing Haiku.
    Only triggers when response is substantive AND contains analysis keywords.
    """
    if len(assistant_response) < 300:
        return []

    # Guard 1: must contain analysis keywords
    if not any(kw in assistant_response for kw in _ANALYSIS_KEYWORDS):
        return []

    # Guard 2: must contain at least one uppercase ticker-like word not in skip list
    tickers_found = {
        m for m in _TICKER_PATTERN.findall(assistant_response)
        if m not in _SKIP_WORDS
    }
    if not tickers_found:
        return []

    try:
        extraction = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "Extract stock analyses from this assistant response.\n"
                    "Return ONLY valid JSON array, nothing else.\n\n"
                    'Format: [{"ticker":"AAPL","thesis_type":"bull|bear|neutral","thesis":"one sentence"}]\n'
                    "If no specific stocks were analyzed with a recommendation, return: []\n\n"
                    f"Assistant response:\n{assistant_response[:2000]}"
                )
            }]
        )
        raw = extraction.content[0].text.strip()
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return []
        return [
            a for a in json.loads(match.group())
            if isinstance(a.get("ticker"), str)
            and 1 <= len(a["ticker"]) <= 5
            and a["ticker"].upper() not in _SKIP_WORDS
            and a.get("thesis")
        ]
    except Exception:
        return []


def _persist_analyses(user_id: int, analyses: list):
    from datetime import datetime
    for a in analyses:
        ticker = a["ticker"].upper()
        thesis = a.get("thesis", "")
        thesis_type = a.get("thesis_type", "neutral")
        mysql_memory.add_to_watchlist(user_id, ticker)
        chroma_id = f"thesis-{ticker}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        thesis_id = mysql_memory.save_thesis(
            ticker=ticker, thesis=thesis, thesis_type=thesis_type,
            source="conversation", chroma_doc_id=chroma_id,
        )
        add_knowledge(
            chroma_id,
            f"[{thesis_type.upper()} thesis for {ticker}] {thesis}",
            metadata={"ticker": ticker, "thesis_type": thesis_type,
                      "credibility": 0.5, "thesis_id": thesis_id, "type": "stock_thesis"},
        )


# ── Main chat function ────────────────────────────────────────────────────────

def chat(user_id: int, user_message: str) -> str:
    """
    Optimized chat with prompt caching on the static persona section.
    Dynamic parts (RAG, user profile) remain uncached as they change per query.
    """
    # Optimization 2: split system prompt into cacheable static + dynamic parts
    static_persona = build_static_persona()
    dynamic_context = build_system_prompt(user_id, user_message)

    # Use cache_control on the large static section — pay full price once, 10% on hits
    system = [
        {
            "type": "text",
            "text": static_persona,
            "cache_control": {"type": "ephemeral"},  # cached for 5 min TTL
        },
        {
            "type": "text",
            "text": dynamic_context,
        },
    ]

    history = redis_memory.get_history(user_id)

    # Optimization 3: trim RAG from history to avoid sending it repeatedly
    # Only keep role/content, strip any injected context from old turns
    messages = history + [{"role": "user", "content": user_message}]

    # Agentic loop
    while True:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=messages,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_output = _dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            final_text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            # Log cache performance
            usage = response.usage
            if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
                logger.info(
                    f"Tokens — input: {usage.input_tokens}, "
                    f"cache_read: {usage.cache_read_input_tokens}, "
                    f"cache_write: {getattr(usage, 'cache_creation_input_tokens', 0)}, "
                    f"output: {usage.output_tokens}"
                )
            break

    # Persist
    redis_memory.append_turn(user_id, "user", user_message)
    redis_memory.append_turn(user_id, "assistant", final_text)
    mysql_memory.save_conversation_turn(user_id, "user", user_message)
    mysql_memory.save_conversation_turn(user_id, "assistant", final_text)

    # Background enrichment — never blocks response
    try:
        analyses = _extract_analyses(user_message, final_text)
        if analyses:
            _persist_analyses(user_id, analyses)
    except Exception:
        pass

    return final_text
