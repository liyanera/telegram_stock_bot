"""
PNL calculation engine.
Computes daily + cumulative PNL for both plan types.
"""
import json
import logging
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from trading.schema import (
    get_positions, get_or_create_portfolio, save_daily_pnl,
    get_cumulative_pnl, get_weekly_turnover, Session, text
)
from trading.prices import get_prices_batch, calculate_gmv

logger = logging.getLogger(__name__)


def calculate_daily_pnl(
    plan_type: str,
    trade_date: str,
    price_type: str = "close",
    portfolio_name: str = "main",
) -> dict:
    """
    Calculate end-of-day PNL for a given plan.

    For each position:
      Daily P&L contribution = (close_price - avg_cost) × shares
      Realized P&L = from sells during the day (close_price - avg_cost_at_sell × shares)
    """
    positions = get_positions(portfolio_name)
    portfolio = get_or_create_portfolio(portfolio_name)
    cash = portfolio["cash"]

    if not positions:
        logger.info(f"{plan_type}: No positions — PNL = $0")
        return {"plan_type": plan_type, "daily_pnl": 0, "cumulative_pnl": 0,
                "portfolio_value": cash, "gmv": 0, "positions": []}

    tickers = [p["ticker"] for p in positions]
    prices = get_prices_batch(tickers, price_type)

    unrealized_pnl = 0.0
    position_details = []

    for pos in positions:
        ticker = pos["ticker"]
        close = prices.get(ticker)
        if not close:
            close = pos["avg_cost"]  # fallback if price unavailable

        unrealized = (close - pos["avg_cost"]) * pos["shares"]
        unrealized_pnl += unrealized
        pnl_pct = (close - pos["avg_cost"]) / pos["avg_cost"] * 100 if pos["avg_cost"] else 0

        position_details.append({
            "ticker": ticker,
            "shares": pos["shares"],
            "avg_cost": pos["avg_cost"],
            "close_price": close,
            "market_value": pos["shares"] * close,
            "unrealized_pnl": unrealized,
            "pnl_pct": pnl_pct,
        })

    # Realized PNL from today's sells
    realized_pnl = _get_realized_pnl(trade_date, plan_type)

    gmv = sum(p["shares"] * prices.get(p["ticker"], p["avg_cost"]) for p in positions)
    portfolio_value = cash + gmv
    daily_pnl = realized_pnl + unrealized_pnl

    # Weekly turnover
    weekly_turnover = get_weekly_turnover(trade_date)

    # Today's turnover
    with Session() as s:
        row = s.execute(
            text("SELECT COALESCE(SUM(ABS(notional)), 0) FROM pt_orders "
                 "WHERE trade_date=:d AND plan_type=:pt"),
            {"d": trade_date, "pt": plan_type}
        ).first()
        today_turnover = float(row[0]) if row else 0.0

    # Previous cumulative PNL + today
    prev_cumulative = get_cumulative_pnl(plan_type)
    cumulative_pnl = prev_cumulative + daily_pnl

    # Save to DB
    save_daily_pnl(
        trade_date=trade_date, plan_type=plan_type,
        realized=realized_pnl, unrealized=unrealized_pnl,
        cumulative=cumulative_pnl, portfolio_value=portfolio_value,
        gmv=gmv, turnover=today_turnover, weekly_turnover=weekly_turnover
    )

    result = {
        "plan_type": plan_type,
        "trade_date": trade_date,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "daily_pnl": daily_pnl,
        "cumulative_pnl": cumulative_pnl,
        "portfolio_value": portfolio_value,
        "cash": cash,
        "gmv": gmv,
        "turnover_today": today_turnover,
        "return_pct": (portfolio_value - 1_000_000) / 1_000_000 * 100,
        "positions": position_details,
    }

    logger.info(
        f"{plan_type} PNL ({trade_date}): "
        f"daily ${daily_pnl:+,.0f} | cumulative ${cumulative_pnl:+,.0f} | "
        f"portfolio ${portfolio_value:,.0f} ({result['return_pct']:+.2f}%)"
    )

    return result


def _get_realized_pnl(trade_date: str, plan_type: str) -> float:
    """Calculate realized PNL from sells today using avg_cost vs execution_price."""
    with Session() as s:
        rows = s.execute(
            text("SELECT o.ticker, o.shares, o.execution_price, "
                 "p.avg_cost FROM pt_orders o "
                 "LEFT JOIN pt_positions p ON o.ticker = p.ticker "
                 "WHERE o.trade_date=:d AND o.action='SELL' AND o.plan_type=:pt"),
            {"d": trade_date, "pt": plan_type}
        ).fetchall()

    realized = 0.0
    for row in rows:
        _, shares, exec_price, avg_cost = row
        if avg_cost:
            realized += (exec_price - avg_cost) * shares
    return realized


def compare_plans(trade_date: str) -> dict:
    """Compare PNL between pre_open and pre_close plans."""
    with Session() as s:
        pre_open = s.execute(
            text("SELECT daily_pnl, cumulative_pnl, portfolio_value, gmv, turnover "
                 "FROM pt_daily_pnl WHERE trade_date=:d AND plan_type='pre_open' "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"d": trade_date}
        ).first()
        pre_close = s.execute(
            text("SELECT daily_pnl, cumulative_pnl, portfolio_value, gmv, turnover "
                 "FROM pt_daily_pnl WHERE trade_date=:d AND plan_type='pre_close' "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"d": trade_date}
        ).first()

    return {
        "trade_date": trade_date,
        "pre_open": {
            "daily_pnl": pre_open[0] if pre_open else 0,
            "cumulative_pnl": pre_open[1] if pre_open else 0,
            "portfolio_value": pre_open[2] if pre_open else 0,
        } if pre_open else None,
        "pre_close": {
            "daily_pnl": pre_close[0] if pre_close else 0,
            "cumulative_pnl": pre_close[1] if pre_close else 0,
            "portfolio_value": pre_close[2] if pre_close else 0,
        } if pre_close else None,
        "winner": (
            "pre_open" if (pre_open and pre_close and pre_open[0] > pre_close[0])
            else "pre_close" if (pre_open and pre_close and pre_close[0] > pre_open[0])
            else "tie"
        ),
    }
