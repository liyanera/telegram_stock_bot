from telegram import Update
from telegram.ext import ContextTypes
from memory import mysql_memory, redis_memory


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show paper trading portfolio status."""
    try:
        from trading.schema import init_trading_db, get_or_create_portfolio, get_positions, get_pnl_history
        from trading.prices import get_prices_batch, calculate_gmv
        init_trading_db()

        portfolio = get_or_create_portfolio("main")
        positions = get_positions("main")
        cash = portfolio["cash"]
        initial = portfolio["initial_capital"]

        if positions:
            tickers = [p["ticker"] for p in positions]
            prices = get_prices_batch(tickers, "realtime")
            gmv = calculate_gmv(positions, prices)
        else:
            prices = {}
            gmv = 0

        total_value = cash + gmv
        total_return = (total_value - initial) / initial * 100

        pos_lines = ""
        for p in positions:
            price = prices.get(p["ticker"], p["avg_cost"])
            mkt_val = p["shares"] * price
            pnl = mkt_val - p["shares"] * p["avg_cost"]
            pnl_pct = pnl / (p["shares"] * p["avg_cost"]) * 100 if p["avg_cost"] else 0
            icon = "✅" if pnl >= 0 else "❌"
            pos_lines += (
                f"\n{icon} <b>{p['ticker']}</b>: <code>{p['shares']:.0f}</code>sh "
                f"@ <code>${p['avg_cost']:.2f}</code> → <code>${price:.2f}</code> "
                f"(<code>{pnl_pct:+.1f}%</code>)"
            )

        pnl_history = get_pnl_history("pre_open", days=5)
        pnl_lines = ""
        for h in pnl_history[-5:]:
            icon = "📈" if h["daily_pnl"] >= 0 else "📉"
            pnl_lines += f"\n{icon} {h['date']}: <code>${h['daily_pnl']:+,.0f}</code>"

        sign = "+" if total_return >= 0 else ""
        reply = (
            f"<b>📊 Paper Trading Portfolio</b>\n\n"
            f"<b>💰 Value</b>: <code>${total_value:,.0f}</code> "
            f"(<code>{sign}{total_return:.2f}%</code>)\n"
            f"<b>💵 Cash</b>: <code>${cash:,.0f}</code>\n"
            f"<b>📦 GMV</b>: <code>${gmv:,.0f}</code>\n"
            f"<b>🏦 Initial</b>: <code>${initial:,.0f}</code>\n"
        )

        if pos_lines:
            reply += f"\n<b>Positions ({len(positions)})</b>:{pos_lines}\n"
        else:
            reply += "\n<i>No open positions</i>\n"

        if pnl_lines:
            reply += f"\n<b>Recent PNL</b>:{pnl_lines}\n"

        await update.message.reply_text(reply, parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"Error loading portfolio: {e}")


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
