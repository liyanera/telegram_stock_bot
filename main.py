import logging
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from bot.handlers import handle_message
from bot.commands import (
    cmd_start, cmd_help, cmd_watchlist,
    cmd_add, cmd_remove, cmd_risk, cmd_clear, cmd_portfolio,
)
from memory.mysql_memory import init_db
from memory.redis_memory import ping as redis_ping
from memory.vector_memory import add_knowledge_bulk
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import config
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _seed_knowledge():
    """Auto-seed ChromaDB from knowledge/ on every startup."""
    knowledge_dir = Path(__file__).parent / "knowledge"
    docs = []
    for filepath in sorted(knowledge_dir.glob("**/*.md")) + sorted(knowledge_dir.glob("**/*.txt")):
        text = filepath.read_text(encoding="utf-8")
        words = text.split()
        chunk_size, overlap = 500, 50
        i = 0
        while i < len(words):
            chunk = " ".join(words[i: i + chunk_size])
            docs.append({
                "id": f"{filepath.stem}_{i}",
                "text": chunk,
                "metadata": {"source": filepath.name},
            })
            i += chunk_size - overlap
    if docs:
        add_knowledge_bulk(docs)
        logger.info(f"Knowledge base seeded: {len(docs)} chunks from {knowledge_dir}")


def _run_weekly_research():
    logger.info("Running weekly research...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.weekly_research import main as research_main
        research_main()
        logger.info("Weekly research completed.")
    except Exception as e:
        logger.error(f"Weekly research failed: {e}")


def _run_weekly_monitor():
    logger.info("Running weekly price monitor...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.weekly_monitor import run_monitor
        run_monitor()
        logger.info("Weekly monitor completed.")
    except Exception as e:
        logger.error(f"Weekly monitor failed: {e}")


def _run_daily_premarket():
    logger.info("Running daily pre-market news tracker...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.daily_premarket import run_daily_premarket
        run_daily_premarket()
        logger.info("Pre-market tracker completed.")
    except Exception as e:
        logger.error(f"Pre-market tracker failed: {e}")


def _run_trading_preopen():
    logger.info("Running pre-open trading agent...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.trading_preopen import run_preopen
        run_preopen()
    except Exception as e:
        logger.error(f"Pre-open trading failed: {e}")


def _run_trading_preclose():
    logger.info("Running pre-close trading agent...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.trading_preclose import run_preclose
        run_preclose()
    except Exception as e:
        logger.error(f"Pre-close trading failed: {e}")


def _run_trading_eod():
    logger.info("Running EOD PNL calculation...")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.trading_eod import run_eod
        run_eod()
    except Exception as e:
        logger.error(f"EOD PNL failed: {e}")


def _start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    # Daily pre-market: Mon-Fri 13:00 UTC (9:00 AM ET, 30 min before open)
    scheduler.add_job(
        _run_daily_premarket,
        CronTrigger(day_of_week="mon-fri", hour=13, minute=0),
        id="daily_premarket",
        name="Daily pre-market watchlist news + macro briefing",
        replace_existing=True,
    )

    # Weekly research: every Monday 08:00 UTC
    scheduler.add_job(
        _run_weekly_research,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_research",
        name="Weekly top-gainer research + undervalued picks",
        replace_existing=True,
    )

    # Weekly monitor: every Monday 09:00 UTC (after research finishes)
    scheduler.add_job(
        _run_weekly_monitor,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_monitor",
        name="Weekly price change + thesis credibility update",
        replace_existing=True,
    )

    # Paper trading: pre-open Mon-Fri 13:20 UTC (9:20 AM ET)
    scheduler.add_job(
        _run_trading_preopen,
        CronTrigger(day_of_week="mon-fri", hour=13, minute=20),
        id="trading_preopen",
        name="Paper trading pre-open rebalancing",
        replace_existing=True,
    )

    # Paper trading: pre-close Mon-Fri 19:30 UTC (3:30 PM ET)
    scheduler.add_job(
        _run_trading_preclose,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=30),
        id="trading_preclose",
        name="Paper trading pre-close rebalancing",
        replace_existing=True,
    )

    # Paper trading: EOD PNL Mon-Fri 21:00 UTC (5:00 PM ET)
    scheduler.add_job(
        _run_trading_eod,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0),
        id="trading_eod",
        name="Paper trading EOD PNL calculation",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started — "
        "pre-market Mon-Fri 13:00 UTC | "
        "trading pre-open 13:20 UTC | "
        "trading pre-close 19:30 UTC | "
        "trading EOD 21:00 UTC | "
        "weekly research Mon 08:00 UTC | "
        "monitor Mon 09:00 UTC"
    )
    return scheduler


def main():
    logger.info("Initializing database...")
    init_db()

    if redis_ping():
        logger.info("Redis connected.")
    else:
        logger.warning("Redis not reachable — working memory disabled.")

    logger.info("Seeding knowledge base...")
    _seed_knowledge()

    logger.info("Starting weekly scheduler...")
    scheduler = _start_scheduler()

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Listening...")
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
