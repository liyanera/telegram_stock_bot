import json
import re
import anthropic
import config
from claude.tools import TOOLS
from claude.prompts import build_system_prompt
from memory import redis_memory, mysql_memory
from memory.vector_memory import add_knowledge, search as knowledge_search
from data.stocks import get_stock_price, get_financials, get_technical_indicators
from data.news import get_stock_news

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Tickers that are common English words — skip these to avoid false positives
_SKIP_WORDS = {"A", "AT", "BE", "BY", "GO", "HI", "IF", "IN", "IS", "IT",
               "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE"}


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
        elif tool_name == "search_knowledge_base":
            chunks = knowledge_search(tool_input["query"])
            result = [c["text"] for c in chunks] if chunks else ["No relevant knowledge found."]
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _extract_analyses(user_message: str, assistant_response: str) -> list[dict]:
    """
    Use Claude Haiku to extract any stock tickers that were meaningfully analyzed,
    along with a one-sentence thesis for each. Only triggers for substantive responses.
    Returns: [{"ticker": "AAPL", "thesis_type": "bull", "thesis": "..."}]
    """
    if len(assistant_response) < 300:
        return []

    # Quick check: does the response look like a stock analysis?
    has_stock_indicators = any(kw in assistant_response for kw in [
        "P/E", "revenue", "growth", "RSI", "MACD", "margin", "bullish", "bearish",
        "buy", "sell", "target", "catalyst", "thesis", "valuation", "%"
    ])
    if not has_stock_indicators:
        return []

    try:
        extraction = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Extract stock analyses from this assistant response.
Return ONLY valid JSON array, nothing else.

Format: [{{"ticker": "AAPL", "thesis_type": "bull|bear|neutral", "thesis": "one sentence reason"}}]

If no specific stocks were analyzed with a recommendation, return: []

Assistant response:
{assistant_response[:2000]}"""
            }]
        )
        raw = extraction.content[0].text.strip()
        # Extract JSON array from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return []
        analyses = json.loads(match.group())
        # Filter out false positives
        return [
            a for a in analyses
            if isinstance(a.get("ticker"), str)
            and 1 <= len(a["ticker"]) <= 5
            and a["ticker"].upper() not in _SKIP_WORDS
            and a.get("thesis")
        ]
    except Exception:
        return []


def _persist_analyses(user_id: int, analyses: list[dict]):
    """Auto-add tickers to watchlist and save theses to DB + ChromaDB."""
    for a in analyses:
        ticker = a["ticker"].upper()
        thesis = a.get("thesis", "")
        thesis_type = a.get("thesis_type", "neutral")

        # 1. Auto-add to watchlist
        mysql_memory.add_to_watchlist(user_id, ticker)

        # 2. Save thesis to MySQL
        from datetime import datetime
        chroma_id = f"thesis-{ticker}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        thesis_id = mysql_memory.save_thesis(
            ticker=ticker,
            thesis=thesis,
            thesis_type=thesis_type,
            source="conversation",
            chroma_doc_id=chroma_id,
        )

        # 3. Save to ChromaDB with credibility metadata
        add_knowledge(
            chroma_id,
            f"[{thesis_type.upper()} thesis for {ticker}] {thesis}",
            metadata={
                "ticker": ticker,
                "thesis_type": thesis_type,
                "credibility": 0.5,
                "thesis_id": thesis_id,
                "type": "stock_thesis",
            },
        )


def chat(user_id: int, user_message: str) -> str:
    """
    Send a message and return Claude's response.
    - Manages Redis working memory and MySQL persistent log
    - Handles multi-turn tool use automatically
    - Auto-extracts stock analyses → watchlist + thesis DB
    """
    system_prompt = build_system_prompt(user_id, user_message)
    history = redis_memory.get_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]

    # Agentic loop
    while True:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
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
            break

    # Persist conversation
    redis_memory.append_turn(user_id, "user", user_message)
    redis_memory.append_turn(user_id, "assistant", final_text)
    mysql_memory.save_conversation_turn(user_id, "user", user_message)
    mysql_memory.save_conversation_turn(user_id, "assistant", final_text)

    # Auto-extract analyses → watchlist + thesis (async-safe: runs in thread executor)
    try:
        analyses = _extract_analyses(user_message, final_text)
        if analyses:
            _persist_analyses(user_id, analyses)
    except Exception:
        pass  # Never block the response for background enrichment

    return final_text
