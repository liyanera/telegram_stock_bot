"""
Pre-close rebalancing agent — runs at 19:30 UTC (3:30 PM ET, 30 min before close).
Cost basis: real-time prices.
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


def run_preclose():
    init_trading_db()
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"\n{'='*60}")
    logger.info(f"PRE-CLOSE Rebalancing — {trade_date} (3:30 PM ET)")
    logger.info(f"{'='*60}")

    portfolio = get_or_create_portfolio("main")
    positions = get_positions("main")
    cash = portfolio["cash"]

    # Price basis: real-time
    all_tickers = list({p["ticker"] for p in positions} | set(UNIVERSE[:20]))
    price_map = get_prices_batch(all_tickers, "realtime")
    price_map = {k: v for k, v in price_map.items() if v}

    gmv = calculate_gmv(positions, price_map)
    portfolio_value = cash + gmv
    weekly_turnover = get_weekly_turnover(trade_date)

    # Today's turnover already used by pre-open
    from trading.schema import Session, text
    with Session() as s:
        row = s.execute(
            text("SELECT COALESCE(SUM(ABS(notional)),0) FROM pt_orders "
                 "WHERE trade_date=:d"), {"d": trade_date}
        ).first()
        today_turnover = float(row[0]) if row else 0.0

    logger.info(f"Portfolio: cash=${cash:,.0f} | GMV=${gmv:,.0f} | total=${portfolio_value:,.0f}")

    plan = generate_rebalancing_plan(
        plan_type="pre_close",
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
    logger.info(f"Proposed trades: {len(plan.get('trades', []))}")

    plan_id = save_plan(
        plan_date=trade_date,
        plan_type="pre_close",
        reasoning=plan.get("reasoning", "") + "\n\nMarket view: " + plan.get("market_view", ""),
        context=str(plan.get("target_positions", []))
    )

    if plan.get("trades"):
        result = execute_plan(
            plan_id=plan_id,
            plan_type="pre_close",
            trades=plan["trades"],
            price_map=price_map,
            price_benchmark="realtime",
            trade_date=trade_date,
        )
        logger.info(f"Executed: {len(result['executed'])} trades")
    else:
        logger.info("No trades — holding current positions.")

    # Notify Telegram group
    import config
    if config.TRADING_GROUP_CHAT_ID:
        from trading.notifier import format_preclose_plan, send_to_group
        pf = get_or_create_portfolio("main")
        new_gmv = calculate_gmv(get_positions("main"), price_map)
        msg = format_preclose_plan(
            plan, result["executed"] if plan.get("trades") else [],
            trade_date, pf["cash"] + new_gmv, pf["cash"], new_gmv
        )
        send_to_group(config.TRADING_GROUP_CHAT_ID, msg)

    logger.info(f"Pre-close rebalancing complete.\n{'='*60}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_preclose()
