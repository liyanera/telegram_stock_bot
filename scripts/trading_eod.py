"""
End-of-day PNL calculation — runs at 21:00 UTC (5:00 PM ET, after market close).
Calculates daily PNL for both plans and compares them.
"""
import sys, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from trading.schema import init_trading_db
from trading.pnl import calculate_daily_pnl, compare_plans
from memory.vector_memory import add_knowledge

logger = logging.getLogger(__name__)


def run_eod():
    init_trading_db()
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"\n{'='*60}")
    logger.info(f"EOD PNL Calculation — {trade_date}")
    logger.info(f"{'='*60}")

    # Calculate PNL for both plans using closing prices
    pre_open_pnl = calculate_daily_pnl("pre_open", trade_date, "close")
    pre_close_pnl = calculate_daily_pnl("pre_close", trade_date, "close")

    # Compare
    comparison = compare_plans(trade_date)
    winner = comparison["winner"]

    logger.info(f"\n{'─'*60}")
    logger.info(f"DAILY PNL COMPARISON — {trade_date}")
    logger.info(f"{'─'*60}")
    logger.info(f"  Pre-Open  Plan: ${pre_open_pnl['daily_pnl']:+,.0f} daily | "
                f"${pre_open_pnl['cumulative_pnl']:+,.0f} cumulative | "
                f"portfolio ${pre_open_pnl['portfolio_value']:,.0f} "
                f"({pre_open_pnl['return_pct']:+.2f}%)")
    logger.info(f"  Pre-Close Plan: ${pre_close_pnl['daily_pnl']:+,.0f} daily | "
                f"${pre_close_pnl['cumulative_pnl']:+,.0f} cumulative | "
                f"portfolio ${pre_close_pnl['portfolio_value']:,.0f} "
                f"({pre_close_pnl['return_pct']:+.2f}%)")
    logger.info(f"  Winner today: {winner.upper()}")
    logger.info(f"{'─'*60}\n")

    # Store in ChromaDB for bot reference
    pos_summary_pre_open = "\n".join(
        f"  {p['ticker']}: {p['shares']:.0f}sh @ ${p['avg_cost']:.2f} → ${p['close_price']:.2f} "
        f"({p['pnl_pct']:+.1f}%)"
        for p in pre_open_pnl.get("positions", [])
    ) or "  No positions"

    doc = (
        f"[PAPER TRADING EOD {trade_date}]\n"
        f"Pre-Open Plan: daily ${pre_open_pnl['daily_pnl']:+,.0f} | "
        f"cumulative ${pre_open_pnl['cumulative_pnl']:+,.0f} | "
        f"return {pre_open_pnl['return_pct']:+.2f}%\n"
        f"Pre-Close Plan: daily ${pre_close_pnl['daily_pnl']:+,.0f} | "
        f"cumulative ${pre_close_pnl['cumulative_pnl']:+,.0f} | "
        f"return {pre_close_pnl['return_pct']:+.2f}%\n"
        f"Winner: {winner}\n"
        f"Positions (pre-open):\n{pos_summary_pre_open}"
    )
    add_knowledge(
        f"paper-trading-eod-{trade_date}",
        doc,
        metadata={"type": "paper_trading_eod", "date": trade_date, "credibility": 0.8}
    )
    logger.info("EOD summary stored to ChromaDB.")

    # Notify Telegram group
    import config
    if config.TRADING_GROUP_CHAT_ID:
        from trading.notifier import format_eod_pnl, send_to_group
        msg = format_eod_pnl(pre_open_pnl, pre_close_pnl, trade_date)
        send_to_group(config.TRADING_GROUP_CHAT_ID, msg)

    return {"pre_open": pre_open_pnl, "pre_close": pre_close_pnl, "comparison": comparison}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_eod()
