"""
Trading constraints — reads from trading_config table at runtime.
Fallback to hardcoded defaults if DB is unavailable.
"""

_DEFAULTS = {
    "max_positions":           10,
    "max_position_pct":        0.20,
    "max_daily_turnover_pct":  0.10,
    "max_weekly_turnover_pct": 0.40,
    "min_trade_notional":      5_000.0,
    "initial_capital":         1_000_000.0,
}


def _get_float(key: str) -> float:
    try:
        from trading.schema import get_trading_config
        val = get_trading_config(key)
        return float(val) if val is not None else _DEFAULTS[key]
    except Exception:
        return _DEFAULTS[key]


def _get_int(key: str) -> int:
    return int(_get_float(key))


def get_max_positions() -> int:       return _get_int("max_positions")
def get_max_position_pct() -> float:  return _get_float("max_position_pct")
def get_max_daily_turnover_pct() -> float:  return _get_float("max_daily_turnover_pct")
def get_max_weekly_turnover_pct() -> float: return _get_float("max_weekly_turnover_pct")
def get_min_trade_notional() -> float: return _get_float("min_trade_notional")
def get_initial_capital() -> float:   return _get_float("initial_capital")


def validate_plan(proposed_trades: list, current_positions: list,
                  portfolio_value: float, gmv: float,
                  today_turnover: float, weekly_turnover: float) -> dict:
    MAX_POSITIONS = get_max_positions()
    MAX_POSITION_PCT = get_max_position_pct()
    MAX_DAILY_TURNOVER_PCT = get_max_daily_turnover_pct()
    MAX_WEEKLY_TURNOVER_PCT = get_max_weekly_turnover_pct()
    MIN_TRADE_NOTIONAL = get_min_trade_notional()

    violations = []
    adjusted = []

    pos_map = {p["ticker"]: p["shares"] for p in current_positions}
    for trade in proposed_trades:
        t = trade["ticker"]
        if trade["action"] == "BUY":
            pos_map[t] = pos_map.get(t, 0) + trade["shares"]
        else:
            pos_map[t] = pos_map.get(t, 0) - trade["shares"]
    open_positions = sum(1 for v in pos_map.values() if v > 0)

    if open_positions > MAX_POSITIONS:
        violations.append(f"Would have {open_positions} positions, max is {MAX_POSITIONS}")

    new_turnover = today_turnover
    for trade in proposed_trades:
        notional = trade["shares"] * trade["price"]
        new_turnover += notional

        new_shares = pos_map.get(trade["ticker"], 0)
        new_notional = new_shares * trade["price"]
        if gmv > 0 and new_notional / portfolio_value > MAX_POSITION_PCT:
            violations.append(
                f"{trade['ticker']}: position would be "
                f"{new_notional/portfolio_value*100:.1f}% of portfolio "
                f"(max {MAX_POSITION_PCT*100:.0f}%)"
            )
        else:
            adjusted.append(trade)

    if gmv > 0 and new_turnover / gmv > MAX_DAILY_TURNOVER_PCT:
        violations.append(
            f"Daily turnover would be {new_turnover/gmv*100:.1f}% of GMV "
            f"(max {MAX_DAILY_TURNOVER_PCT*100:.0f}%)"
        )

    new_weekly = weekly_turnover + new_turnover
    if gmv > 0 and new_weekly / gmv > MAX_WEEKLY_TURNOVER_PCT:
        violations.append(
            f"Weekly turnover would be {new_weekly/gmv*100:.1f}% of GMV "
            f"(max {MAX_WEEKLY_TURNOVER_PCT*100:.0f}%)"
        )

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
        f"Constraints: max {get_max_positions()} positions | "
        f"max {get_max_position_pct()*100:.0f}% per name | "
        f"daily turnover ≤{get_max_daily_turnover_pct()*100:.0f}% GMV | "
        f"weekly turnover ≤{get_max_weekly_turnover_pct()*100:.0f}% GMV"
    )
