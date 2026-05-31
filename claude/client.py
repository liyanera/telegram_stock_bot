import json
import anthropic
import config
from claude.tools import TOOLS
from claude.prompts import build_system_prompt
from memory import redis_memory, mysql_memory
from data.stocks import get_stock_price, get_financials, get_technical_indicators
from data.news import get_stock_news
from memory.vector_memory import search as knowledge_search

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


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


def chat(user_id: int, user_message: str) -> str:
    """
    Send a message and return Claude's response.
    Manages Redis working memory and MySQL persistent log.
    Handles multi-turn tool use automatically.
    """
    system_prompt = build_system_prompt(user_id, user_message)
    history = redis_memory.get_history(user_id)

    messages = history + [{"role": "user", "content": user_message}]

    # Agentic loop: Claude may call tools multiple times before giving a final answer
    while True:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Append assistant message (may contain text + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
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
            # Final text response
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            break

    # Persist to Redis (working memory)
    redis_memory.append_turn(user_id, "user", user_message)
    redis_memory.append_turn(user_id, "assistant", final_text)

    # Persist to MySQL (long-term log)
    mysql_memory.save_conversation_turn(user_id, "user", user_message)
    mysql_memory.save_conversation_turn(user_id, "assistant", final_text)

    return final_text
