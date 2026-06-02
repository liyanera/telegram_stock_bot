"""
AI Trading Agent — uses Claude to generate rebalancing plans.
"""
import json
import re
import logging
from datetime import datetime
import anthropic
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from trading.constraints import (
    MAX_POSITIONS, MAX_POSITION_PCT, MAX_DAILY_TURNOVER_PCT,
    MAX_WEEKLY_TURNOVER_PCT, INITIAL_CAPITAL, constraints_summary
)
from memory.vector_memory import search as knowledge_search

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

UNIVERSE = [
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","AVGO","CRM","ORCL",
    "AMD","PLTR","SNOW","DDOG","NET","CRWD","ANET","ZS","MDB","HUBS",
    "WDAY","NOW","TTD","SHOP","UBER","ABNB","HOOD","SOFI","COIN",
    "LLY","REGN","VRTX","MRVL","ARM","SMCI","GTLB","FTNT","FSLR","CEG",
]


def _get_market_context() -> str:
    """Pull latest macro briefing and news from ChromaDB."""
    chunks = knowledge_search("pre-market macro briefing stock analysis", n_results=3)
    if not chunks:
        return "No recent market context available."
    return "\n\n".join(c["text"] for c in chunks)


def generate_rebalancing_plan(
    plan_type: str,          # "pre_open" or "pre_close"
    current_positions: list, # [{ticker, shares, avg_cost, plan_type}]
    cash: float,
    portfolio_value: float,
    gmv: float,
    price_map: dict,         # {ticker: current_price}
    today_turnover: float,
    weekly_turnover: float,
    trade_date: str,
) -> dict:
    """
    Ask Claude to generate a rebalancing plan.
    Returns: {
        reasoning: str,
        trades: [{ticker, action, shares, price, notional, rationale}],
        expected_positions: [{ticker, target_pct}],
        market_view: str
    }
    """
    # Build current portfolio summary
    positions_text = ""
    if current_positions:
        for p in current_positions:
            price = price_map.get(p["ticker"], p["avg_cost"])
            mkt_val = p["shares"] * price
            cost_val = p["shares"] * p["avg_cost"]
            pnl = mkt_val - cost_val
            pnl_pct = pnl / cost_val * 100 if cost_val else 0
            positions_text += (
                f"  {p['ticker']}: {p['shares']:.0f} shares @ cost ${p['avg_cost']:.2f} | "
                f"current ${price:.2f} | MktVal ${mkt_val:,.0f} | "
                f"PnL ${pnl:+,.0f} ({pnl_pct:+.1f}%)\n"
            )
    else:
        positions_text = "  [No current positions — deploy full capital]\n"

    price_text = "\n".join(
        f"  {t}: ${p:.2f}" for t, p in sorted(price_map.items()) if p
    )

    market_ctx = _get_market_context()

    timing_note = (
        "PRE-OPEN (9:20 AM ET): Orders will execute at open. "
        "Cost basis = previous close prices provided."
        if plan_type == "pre_open" else
        "PRE-CLOSE (3:30 PM ET): Orders will execute near close. "
        "Cost basis = current real-time prices provided."
    )

    prompt = f"""You are an elite US growth stock portfolio manager running a $1M paper trading account.
Today: {trade_date} | Session: {timing_note}

## Current Portfolio
Cash: ${cash:,.0f}
GMV: ${gmv:,.0f}
Portfolio Value: ${portfolio_value:,.0f}

Positions:
{positions_text}

## Available Universe Prices
{price_text}

## Market Context (from pre-market briefing)
{market_ctx}

## Constraints ({constraints_summary()})
- Max {MAX_POSITIONS} single name positions
- Max {MAX_POSITION_PCT*100:.0f}% per name (= ${portfolio_value * MAX_POSITION_PCT:,.0f})
- Daily turnover used: ${today_turnover:,.0f} | limit: ${gmv * MAX_DAILY_TURNOVER_PCT:,.0f}
- Weekly turnover used: ${weekly_turnover:,.0f} | limit: ${gmv * MAX_WEEKLY_TURNOVER_PCT:,.0f}

## Task
Generate a rebalancing plan. Be selective — only trade when conviction is high.
Consider: sector concentration, momentum, news catalysts, macro environment.
Prefer high-quality growth stocks with strong fundamentals and positive momentum.

Return ONLY valid JSON:
{{
  "market_view": "2-3 sentence view on today's market conditions",
  "reasoning": "3-4 sentence portfolio strategy rationale",
  "trades": [
    {{
      "ticker": "NVDA",
      "action": "BUY",
      "shares": 100,
      "price": 1208.50,
      "notional": 120850,
      "rationale": "one sentence why"
    }}
  ],
  "target_positions": [
    {{"ticker": "NVDA", "target_pct": 15.0, "conviction": "high"}}
  ],
  "holds": ["AAPL", "META"],
  "exits": [{{"ticker": "OLD_STOCK", "reason": "why exiting"}}]
}}

trades array can be empty [] if no changes are warranted."""

    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            logger.error("Agent returned no valid JSON")
            return {"reasoning": raw, "trades": [], "target_positions": [], "market_view": ""}
        plan = json.loads(match.group())
        logger.info(
            f"Plan {plan_type} generated: {len(plan.get('trades', []))} trades | "
            f"view: {plan.get('market_view','')[:80]}"
        )
        return plan
    except Exception as e:
        logger.error(f"Agent generation failed: {e}")
        return {"reasoning": str(e), "trades": [], "target_positions": [], "market_view": ""}
