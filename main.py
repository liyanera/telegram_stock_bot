import logging
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from bot.handlers import handle_message
from bot.commands import (
    cmd_start, cmd_help, cmd_watchlist,
    cmd_add, cmd_remove, cmd_risk, cmd_clear,
)
from memory.mysql_memory import init_db
from memory.redis_memory import ping as redis_ping
from memory.vector_memory import add_knowledge_bulk
import config
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _seed_knowledge():
    """Auto-seed ChromaDB from knowledge/ on every startup (safe on Railway redeploys)."""
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


def main():
    logger.info("Initializing database...")
    init_db()

    if redis_ping():
        logger.info("Redis connected.")
    else:
        logger.warning("Redis not reachable — working memory disabled.")

    logger.info("Seeding knowledge base...")
    _seed_knowledge()

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
