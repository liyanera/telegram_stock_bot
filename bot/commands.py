from telegram import Update
from telegram.ext import ContextTypes
from memory import mysql_memory, redis_memory


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    mysql_memory.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    await update.message.reply_text(
        f"Hello {user.first_name}! I'm your personal stock analysis assistant powered by Claude.\n\n"
        "Ask me anything about stocks — prices, technical analysis, fundamentals, news, or strategy.\n\n"
        "Commands:\n"
        "/watchlist — view your watchlist\n"
        "/add TICKER — add stock to watchlist\n"
        "/remove TICKER — remove from watchlist\n"
        "/risk conservative|moderate|aggressive — set risk profile\n"
        "/clear — clear conversation memory\n"
        "/help — show this message"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Stock Analysis Bot Commands:\n\n"
        "/watchlist — view your tracked stocks\n"
        "/add AAPL — add AAPL to watchlist\n"
        "/remove AAPL — remove AAPL from watchlist\n"
        "/risk moderate — set your risk tolerance (conservative/moderate/aggressive)\n"
        "/clear — clear conversation memory (fresh start)\n\n"
        "Just type any question to get stock analysis!\n"
        "Examples:\n"
        "- What's the current price of TSLA?\n"
        "- Analyze NVDA fundamentals\n"
        "- Is AAPL oversold based on RSI?\n"
        "- Give me a full breakdown of MSFT"
    )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tickers = mysql_memory.get_watchlist(user_id)
    if not tickers:
        await update.message.reply_text("Your watchlist is empty. Use /add TICKER to add stocks.")
    else:
        await update.message.reply_text("Your watchlist:\n" + "\n".join(f"• {t}" for t in tickers))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /add TICKER (e.g. /add AAPL)")
        return
    ticker = context.args[0].upper()
    mysql_memory.add_to_watchlist(user_id, ticker)
    await update.message.reply_text(f"Added {ticker} to your watchlist.")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /remove TICKER (e.g. /remove AAPL)")
        return
    ticker = context.args[0].upper()
    mysql_memory.remove_from_watchlist(user_id, ticker)
    await update.message.reply_text(f"Removed {ticker} from your watchlist.")


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    valid = {"conservative", "moderate", "aggressive"}
    if not context.args or context.args[0].lower() not in valid:
        await update.message.reply_text(
            "Usage: /risk conservative|moderate|aggressive"
        )
        return
    level = context.args[0].lower()
    mysql_memory.update_risk_tolerance(user_id, level)
    await update.message.reply_text(f"Risk tolerance set to: {level}")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    redis_memory.clear_history(user_id)
    await update.message.reply_text("Conversation memory cleared. Fresh start!")
