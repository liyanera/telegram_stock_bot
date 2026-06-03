"""
Pre-open rebalancing agent — runs at 13:20 UTC (9:20 AM ET, 10 min before open).
Cost basis: previous day's closing prices.
"""
import sys, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from trading.schema import init_trading_db, get_or_create_portfolio, get_positions, save_plan
from trading.agent import generate_rebalancing_plan, UNIVERSE
from trading.executor import execute_plan
from trading.prices import get_prices_batch, calculate_gmv
from trading.schema import get_weekly_turnover

logger = logging.getLogger(__name__)


def run_preopen():
    init_trading_db()
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"\n{'='*60}")
    logger.info(f"PRE-OPEN Rebalancing — {trade_date} (9:20 AM ET)")
    logger.info(f"{'='*60}")

    portfolio = get_or_create_portfolio("main")
    positions = get_positions("main")
    cash = portfolio["cash"]

    # Price basis: previous close
    all_tickers = list({p["ticker"] for p in positions} | set(UNIVERSE[:20]))
    price_map = get_prices_batch(all_tickers, "prev_close")
    price_map = {k: v for k, v in price_map.items() if v}

    gmv = calculate_gmv(positions, price_map)
    portfolio_value = cash + gmv
    today_turnover = 0.0
    weekly_turnover = get_weekly_turnover(trade_date)

    logger.info(f"Portfolio: cash=${cash:,.0f} | GMV=${gmv:,.0f} | total=${portfolio_value:,.0f}")
    logger.info(f"Positions: {len(positions)} | Weekly turnover: ${weekly_turnover:,.0f}")

    # Generate AI plan
    plan = generate_rebalancing_plan(
        plan_type="pre_open",
        current_positions=positions,
        cash=cash,
        portfolio_value=portfolio_value,
        gmv=gmv,
        price_map=price_map,
        today_turnover=today_turnover,
        weekly_turnover=weekly_turnover,
        trade_date=trade_date,
    )

    logger.info(f"Market view: {plan.get('market_view','')}")
    logger.info(f"Reasoning: {plan.get('reasoning','')}")
    logger.info(f"Proposed trades: {len(plan.get('trades', []))}")

    # Save plan to DB
    plan_id = save_plan(
        plan_date=trade_date,
        plan_type="pre_open",
        reasoning=plan.get("reasoning", "") + "\n\nMarket view: " + plan.get("market_view", ""),
        context=str(plan.get("target_positions", []))
    )

    # Execute trades
    executed = []
    if plan.get("trades"):
        result = execute_plan(
            plan_id=plan_id,
            plan_type="pre_open",
            trades=plan["trades"],
            price_map=price_map,
            price_benchmark="prev_close",
            trade_date=trade_date,
        )
        executed = result["executed"]
        logger.info(f"Executed: {len(executed)} trades | Skipped: {len(result['skipped'])}")
        if result["violations"]:
            logger.warning(f"Violations: {result['violations']}")
    else:
        logger.info("No trades — holding current positions.")

    # Notify Telegram group
    final = get_or_create_portfolio("main")
    new_gmv = sum(t["notional"] for t in executed) if executed else gmv
    _notify_group(plan, executed, trade_date, final["cash"], new_gmv,
                  final["cash"] + new_gmv)

    logger.info(f"Pre-open rebalancing complete.\n{'='*60}\n")


def _notify_group(plan, executed, trade_date, cash, gmv, portfolio_value):
    import config
    if not config.TRADING_GROUP_CHAT_ID:
        return
    from trading.notifier import format_preopen_plan, send_to_group
    msg = format_preopen_plan(plan, executed, trade_date, portfolio_value, cash, gmv)
    send_to_group(config.TRADING_GROUP_CHAT_ID, msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_preopen()
