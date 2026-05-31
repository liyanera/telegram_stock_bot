import logging
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from bot.handlers import handle_message
from bot.commands import (
    cmd_start, cmd_help, cmd_watchlist,
    cmd_add, cmd_remove, cmd_risk, cmd_clear,
)
from memory.mysql_memory import init_db
from memory.redis_memory import ping as redis_ping
import config

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Initializing database...")
    init_db()

    if redis_ping():
        logger.info("Redis connected.")
    else:
        logger.warning("Redis not reachable — working memory disabled.")

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Listening...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
