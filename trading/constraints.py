"""
Trading constraints enforcement.
"""

INITIAL_CAPITAL = 1_000_000.0
MAX_POSITIONS = 10                # max single name count
MAX_POSITION_PCT = 0.20           # max 20% of GMV per name
MAX_DAILY_TURNOVER_PCT = 0.10     # max 10% of GMV per day
MAX_WEEKLY_TURNOVER_PCT = 0.40    # max 40% of GMV per week
MIN_TRADE_NOTIONAL = 5_000        # ignore trades smaller than $5k


def validate_plan(proposed_trades: list, current_positions: list,
                  portfolio_value: float, gmv: float,
                  today_turnover: float, weekly_turnover: float) -> dict:
    """
    Validate a proposed set of trades against all constraints.
    Returns: {valid: bool, violations: [str], adjusted_trades: [dict]}
    """
    violations = []
    adjusted = []

    # Count positions after trades
    pos_map = {p["ticker"]: p["shares"] for p in current_positions}
    for trade in proposed_trades:
        t = trade["ticker"]
        if trade["action"] == "BUY":
            pos_map[t] = pos_map.get(t, 0) + trade["shares"]
        else:
            pos_map[t] = pos_map.get(t, 0) - trade["shares"]
    open_positions = sum(1 for v in pos_map.values() if v > 0)

    # Check max position count
    if open_positions > MAX_POSITIONS:
        violations.append(
            f"Would have {open_positions} positions, max is {MAX_POSITIONS}"
        )

    # Check position size and turnover
    new_turnover = today_turnover
    for trade in proposed_trades:
        notional = trade["shares"] * trade["price"]
        new_turnover += notional

        # Single name position size check
        new_shares = pos_map.get(trade["ticker"], 0)
        new_notional = new_shares * trade["price"]
        if gmv > 0 and new_notional / portfolio_value > MAX_POSITION_PCT:
            violations.append(
                f"{trade['ticker']}: position would be "
                f"{new_notional/portfolio_value*100:.1f}% of portfolio (max {MAX_POSITION_PCT*100:.0f}%)"
            )
        else:
            adjusted.append(trade)

    # Daily turnover
    if gmv > 0 and new_turnover / gmv > MAX_DAILY_TURNOVER_PCT:
        violations.append(
            f"Daily turnover would be {new_turnover/gmv*100:.1f}% of GMV "
            f"(max {MAX_DAILY_TURNOVER_PCT*100:.0f}%)"
        )

    # Weekly turnover
    new_weekly = weekly_turnover + new_turnover
    if gmv > 0 and new_weekly / gmv > MAX_WEEKLY_TURNOVER_PCT:
        violations.append(
            f"Weekly turnover would be {new_weekly/gmv*100:.1f}% of GMV "
            f"(max {MAX_WEEKLY_TURNOVER_PCT*100:.0f}%)"
        )

    # Filter out tiny trades
    adjusted = [t for t in adjusted if t["shares"] * t["price"] >= MIN_TRADE_NOTIONAL]

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "adjusted_trades": adjusted,
        "projected_turnover": new_turnover,
        "projected_positions": open_positions,
    }


def constraints_summary() -> str:
    return (
        f"Constraints: max {MAX_POSITIONS} positions | "
        f"max {MAX_POSITION_PCT*100:.0f}% per name | "
        f"daily turnover ≤{MAX_DAILY_TURNOVER_PCT*100:.0f}% GMV | "
        f"weekly turnover ≤{MAX_WEEKLY_TURNOVER_PCT*100:.0f}% GMV"
    )
