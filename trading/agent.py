"""
AI Trading Agent — focuses on AI industry 4 pillars for risk-adjusted returns.
Pre-open: fundamental + macro driven positioning
Pre-close: intraday momentum + technical confirmation
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
    get_max_positions, get_max_position_pct, get_max_daily_turnover_pct,
    get_max_weekly_turnover_pct, get_initial_capital, constraints_summary
)
from trading.schema import get_universe, get_all_tickers
from memory.vector_memory import search as knowledge_search

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Beta estimates for position sizing (approximate)
BETA_MAP = {
    "NVDA": 1.8, "AMD": 1.7, "SMCI": 2.0, "COHR": 1.6, "MU": 1.5,
    "MRVL": 1.4, "ARM": 1.6, "ANET": 1.3, "AVGO": 1.2, "LRCX": 1.4,
    "KLAC": 1.3, "AMAT": 1.3, "ASML": 1.2, "PLTR": 1.8, "DDOG": 1.6,
    "CEG": 0.8, "VST": 0.9, "TLN": 1.0, "NEE": 0.5, "NRG": 0.9,
    "OKLO": 2.5, "SMR": 2.5, "MSFT": 0.9, "GOOGL": 1.1, "META": 1.2,
    "AMZN": 1.2, "CRWD": 1.5, "NET": 1.5, "NOW": 1.2, "CRM": 1.1,
    "CIEN": 1.2, "LITE": 1.4, "VIAV": 1.0,
}


def _get_market_context() -> str:
    chunks = knowledge_search("pre-market macro briefing AI data center energy photonics", n_results=4)
    if not chunks:
        return "No recent market context available."
    return "\n\n".join(c["text"] for c in chunks)


def _get_ai_framework() -> str:
    chunks = knowledge_search("AI industry data center memory energy photonics risk-adjusted portfolio", n_results=3)
    return "\n\n".join(c["text"] for c in chunks) if chunks else ""


_PILLAR_DESC = {
    "data_center": "Data Center Infrastructure",
    "memory":      "Memory & Semiconductor Equipment (HBM focus)",
    "energy":      "AI Power & Energy Infrastructure",
    "photonics":   "Photonics, Optical & Interconnects",
    "software":    "AI Software & Platform (supporting)",
    "other":       "Other AI-Related",
}


def _build_universe_text(price_map: dict) -> str:
    universe = get_universe()
    lines = []
    for pillar, tickers in universe.items():
        desc = _PILLAR_DESC.get(pillar, pillar)
        lines.append(f"\n[{desc}]")
        for t in tickers:
            price = price_map.get(t)
            beta = BETA_MAP.get(t, 1.2)
            if price:
                lines.append(f"  {t:<6} ${price:>9.2f}  β={beta:.1f}")
    return "\n".join(lines)


def generate_rebalancing_plan(
    plan_type: str,
    current_positions: list,
    cash: float,
    portfolio_value: float,
    gmv: float,
    price_map: dict,
    today_turnover: float,
    weekly_turnover: float,
    trade_date: str,
) -> dict:

    positions_text = ""
    if current_positions:
        for p in current_positions:
            price = price_map.get(p["ticker"], p["avg_cost"])
            mkt_val = p["shares"] * price
            cost_val = p["shares"] * p["avg_cost"]
            pnl = mkt_val - cost_val
            pnl_pct = pnl / cost_val * 100 if cost_val else 0
            beta = BETA_MAP.get(p["ticker"], 1.2)
            pct_of_pf = mkt_val / portfolio_value * 100 if portfolio_value else 0
            positions_text += (
                f"  {p['ticker']:<6} {p['shares']:>5.0f}sh  cost ${p['avg_cost']:>8.2f}  "
                f"now ${price:>8.2f}  PnL {pnl_pct:>+6.1f}%  "
                f"wt {pct_of_pf:.1f}%  β={beta:.1f}\n"
            )
    else:
        positions_text = "  [No positions — deploy $1,000,000 fully]\n"

    market_ctx = _get_market_context()
    ai_framework = _get_ai_framework()

    if plan_type == "pre_open":
        strategy_section = f"""## Strategy: Pre-Open Fundamental Positioning
You are building a 6-12 month risk-adjusted AI portfolio BEFORE market open.
Focus: fundamental conviction, sector allocation, beta-adjusted sizing.

PILLAR ALLOCATION TARGETS:
  Data Center Infrastructure: 40-50% of portfolio
  Memory (HBM/Equipment):     15-20% of portfolio
  Energy (AI Power):          15-20% of portfolio  ← low beta diversifier
  Photonics/Optical:          10-15% of portfolio
  AI Software (optional):     0-10%  of portfolio

RISK-ADJUSTED SIZING RULES:
  Base position = target_weight / beta
  Example: want 15% in NVDA (β=1.8) → actual size = 15/1.8 = 8.3% of portfolio
  Energy names (CEG β=0.8) → can size up to 20% each
  High-beta names (SMCI β=2.0, OKLO β=2.5) → cap at 5-7%
  Target portfolio beta ≤ 1.3 for Sharpe optimization

SELECTION CRITERIA (6-12 month horizon):
  1. Strongest secular AI tailwind in their pillar
  2. Earnings revision momentum (analyst upgrades > downgrades)
  3. Reasonable valuation relative to growth (PEG < 2.0 preferred)
  4. Technical structure: prefer above SMA200
  5. Avoid names with overlapping factor exposure to reduce correlation"""

    else:  # pre_close
        strategy_section = f"""## Strategy: Pre-Close Intraday Momentum Refinement
You are REFINING the portfolio 30 minutes before close using full-day information.
Focus: intraday price action, sector rotation signals, trim losers/add winners.

PRE-CLOSE DECISION RULES:
  1. TRIM: positions down >3% intraday WITHOUT news = weak momentum, trim 20-30%
  2. ADD: positions up >2% intraday WITH volume confirmation = add 10-20%
  3. ROTATE: if a pillar is outperforming today, shift weight toward it
  4. HOLD: do not churn stable positions — respect weekly turnover limit
  5. DEPLOY: if cash exists, add to highest-conviction name with best intraday momentum

INTRADAY SIGNALS TO USE:
  - Price change % today (from cost basis context)
  - Sector ETF performance (XLK, XLE, XLU) as pillar proxy
  - News catalysts that broke during the day
  - Volume: high volume up = institutional accumulation

PRE-CLOSE SIZING:
  Keep same pillar allocation targets as pre-open
  Beta-adjusted sizing still applies
  Smaller adjustments: 5-15% position changes, not wholesale rebuilds"""

    prompt = f"""You are an elite AI industry portfolio manager running a $1M paper trading account.
Target: Best risk-adjusted return over 6-12 month horizon from AI industry ecosystem.
Today: {trade_date}

## Current Portfolio
Cash: ${cash:,.0f}  |  GMV: ${gmv:,.0f}  |  Total: ${portfolio_value:,.0f}

Positions:
{positions_text}

## AI Industry Universe (with prices and beta)
{_build_universe_text(price_map)}

## Market Context
{market_ctx}

## AI Industry Framework (from knowledge base)
{ai_framework[:1500] if ai_framework else 'See pillar descriptions above.'}

## Constraints ({constraints_summary()})
- Max {get_max_positions()} positions
- Max {get_max_position_pct()*100:.0f}% per name
- Daily turnover used: ${today_turnover:,.0f} | limit: ${max(gmv,portfolio_value) * get_max_daily_turnover_pct():,.0f}
- Weekly turnover used: ${weekly_turnover:,.0f} | limit: ${max(gmv,portfolio_value) * get_max_weekly_turnover_pct():,.0f}

{strategy_section}

## MANDATORY
- FULLY INVESTED: deploy ALL cash, target $0 residual cash
- If cash > $5,000 after trades → not enough deployed, add positions
- All trades must serve the 6-12 month AI thesis

Return ONLY valid JSON:
{{
  "market_view": "2-3 sentences on today's AI market conditions",
  "reasoning": "3-4 sentences on portfolio construction rationale",
  "pillar_allocation": {{
    "data_center": 45,
    "memory": 18,
    "energy": 17,
    "photonics": 12,
    "software": 8
  }},
  "trades": [
    {{
      "ticker": "NVDA",
      "action": "BUY",
      "shares": 100,
      "price": 224.36,
      "notional": 22436,
      "pillar": "data_center",
      "rationale": "one sentence"
    }}
  ],
  "holds": ["CEG"],
  "target_portfolio_beta": 1.2
}}"""

    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            logger.error("Agent returned no valid JSON")
            return {"reasoning": raw, "trades": [], "market_view": ""}
        plan = json.loads(match.group())
        logger.info(
            f"Plan {plan_type}: {len(plan.get('trades',[]))} trades | "
            f"target β={plan.get('target_portfolio_beta','?')} | "
            f"allocation={plan.get('pillar_allocation',{})}"
        )
        return plan
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        return {"reasoning": str(e), "trades": [], "market_view": ""}
