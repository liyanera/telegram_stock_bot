"""
Simulated order execution engine.
Applies trades to portfolio, enforces constraints, records orders.
"""
import logging
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from trading.schema import (
    get_or_create_portfolio, update_cash, get_positions,
    upsert_position, save_order, get_weekly_turnover
)
from trading.constraints import validate_plan, get_min_trade_notional

logger = logging.getLogger(__name__)


def execute_plan(
    plan_id: int,
    plan_type: str,
    trades: list,
    price_map: dict,
    price_benchmark: str,
    trade_date: str,
    portfolio_name: str = "main",
) -> dict:
    """
    Execute a list of trades against the simulated portfolio.

    trades: [{ticker, action, shares, price, ...}]
    price_benchmark: the pricing standard used (prev_close/realtime/vwap/etc)

    Returns execution summary.
    """
    portfolio = get_or_create_portfolio(portfolio_name)
    positions = get_positions(portfolio_name)
    cash = portfolio["cash"]

    # Build position map
    pos_map = {p["ticker"]: {"shares": p["shares"], "avg_cost": p["avg_cost"]}
               for p in positions}

    gmv = sum(p["shares"] * price_map.get(p["ticker"], p["avg_cost"])
              for p in positions if price_map.get(p["ticker"]))
    portfolio_value = cash + gmv

    today_turnover = 0.0
    weekly_turnover = get_weekly_turnover(trade_date)

    # Validate constraints
    trades_with_price = []
    for t in trades:
        exec_price = price_map.get(t["ticker"]) or t.get("price")
        if exec_price:
            trades_with_price.append({**t, "price": exec_price})

    validation = validate_plan(
        trades_with_price, positions, portfolio_value, gmv,
        today_turnover, weekly_turnover
    )

    if validation["violations"]:
        logger.warning(f"Constraint violations: {validation['violations']}")

    executed = []
    skipped = []

    for trade in validation["adjusted_trades"]:
        ticker = trade["ticker"]
        action = trade["action"].upper()
        exec_price = price_map.get(ticker) or trade.get("price", 0)
        if not exec_price:
            skipped.append({"ticker": ticker, "reason": "no price available"})
            continue

        shares = abs(trade["shares"])
        notional = shares * exec_price

        if notional < get_min_trade_notional():
            skipped.append({"ticker": ticker, "reason": f"notional ${notional:.0f} below min"})
            continue

        if action == "BUY":
            if notional > cash:
                # Scale down to available cash
                shares = int(cash * 0.99 / exec_price)
                notional = shares * exec_price
                if shares <= 0:
                    skipped.append({"ticker": ticker, "reason": "insufficient cash"})
                    continue

            # Update position with weighted average cost
            existing = pos_map.get(ticker, {"shares": 0, "avg_cost": 0})
            total_shares = existing["shares"] + shares
            if total_shares > 0:
                new_avg_cost = (
                    (existing["shares"] * existing["avg_cost"] + shares * exec_price)
                    / total_shares
                )
            else:
                new_avg_cost = exec_price

            pos_map[ticker] = {"shares": total_shares, "avg_cost": new_avg_cost}
            cash -= notional

        elif action == "SELL":
            existing = pos_map.get(ticker, {"shares": 0, "avg_cost": 0})
            shares = min(shares, existing["shares"])  # can't sell more than owned
            if shares <= 0:
                skipped.append({"ticker": ticker, "reason": "no position to sell"})
                continue

            notional = shares * exec_price
            pos_map[ticker] = {
                "shares": existing["shares"] - shares,
                "avg_cost": existing["avg_cost"]
            }
            cash += notional

        today_turnover += notional

        # Persist order
        save_order(plan_id, plan_type, trade_date, ticker, action,
                   shares, price_benchmark, exec_price)
        executed.append({
            "ticker": ticker, "action": action, "shares": shares,
            "price": exec_price, "notional": notional
        })
        logger.info(f"  {action} {shares:.0f} {ticker} @ ${exec_price:.2f} = ${notional:,.0f}")

    # Persist updated positions
    for ticker, pos in pos_map.items():
        upsert_position(portfolio_name, ticker, pos["shares"],
                        pos["avg_cost"], plan_type)

    update_cash(portfolio_name, cash)

    logger.info(
        f"Execution complete: {len(executed)} trades, ${today_turnover:,.0f} notional | "
        f"cash remaining: ${cash:,.0f}"
    )

    return {
        "executed": executed,
        "skipped": skipped,
        "violations": validation["violations"],
        "today_turnover": today_turnover,
        "cash": cash,
    }
