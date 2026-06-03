"""
Telegram notifications for paper trading events.
"""
import httpx
import config


def send_to_group(chat_id: str, text: str):
    """Send HTML-formatted message to a Telegram group."""
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Telegram notify failed: {e}")
        return False


def format_preopen_plan(plan: dict, executed: list, trade_date: str,
                         portfolio_value: float, cash: float, gmv: float) -> str:
    if not executed and not plan.get("holds") and not plan.get("target_positions"):
        trades_section = "<i>No changes — holding current positions.</i>"
    else:
        rows = ""
        for t in executed:
            action_icon = "🟢 BUY" if t["action"] == "BUY" else "🔴 SELL"
            rows += (
                f"\n{action_icon}  <b>{t['ticker']}</b>  "
                f"<code>{t['shares']:.0f}sh</code>  "
                f"@ <code>${t['price']:.2f}</code>  "
                f"= <code>${t['notional']:,.0f}</code>"
            )
        trades_section = rows if rows else "<i>No trades executed.</i>"

    reason = plan.get("reasoning", "")
    # Trim to one sentence
    reason_short = reason.split(".")[0].strip() + "." if reason else "No reason provided."

    return (
        f"<b>📋 Pre-Open Rebalancing — {trade_date}</b>\n"
        f"<i>9:20 AM ET | Cost basis: prev close</i>\n\n"
        f"<b>Trades</b>:{trades_section}\n\n"
        f"<b>💡 Why:</b> {reason_short}\n\n"
        f"<b>Portfolio</b>: <code>${portfolio_value:,.0f}</code> "
        f"(cash <code>${cash:,.0f}</code> | GMV <code>${gmv:,.0f}</code>)"
    )


def format_preclose_plan(plan: dict, executed: list, trade_date: str,
                          portfolio_value: float, cash: float, gmv: float) -> str:
    rows = ""
    for t in executed:
        action_icon = "🟢 BUY" if t["action"] == "BUY" else "🔴 SELL"
        rows += (
            f"\n{action_icon}  <b>{t['ticker']}</b>  "
            f"<code>{t['shares']:.0f}sh</code>  "
            f"@ <code>${t['price']:.2f}</code>  "
            f"= <code>${t['notional']:,.0f}</code>"
        )

    reason = plan.get("reasoning", "")
    reason_short = reason.split(".")[0].strip() + "." if reason else ""

    return (
        f"<b>📋 Pre-Close Rebalancing — {trade_date}</b>\n"
        f"<i>3:30 PM ET | Cost basis: real-time</i>\n\n"
        f"<b>Trades</b>:{rows if rows else chr(10) + '<i>No changes.</i>'}\n\n"
        f"<b>💡 Why:</b> {reason_short}\n\n"
        f"<b>Portfolio</b>: <code>${portfolio_value:,.0f}</code> "
        f"(cash <code>${cash:,.0f}</code> | GMV <code>${gmv:,.0f}</code>)"
    )


def format_eod_pnl(pre_open: dict, pre_close: dict, trade_date: str) -> str:
    def fmt(plan: dict, label: str) -> str:
        pnl = plan["daily_pnl"]
        cum = plan["cumulative_pnl"]
        ret = plan["return_pct"]
        icon = "📈" if pnl >= 0 else "📉"
        return (
            f"{icon} <b>{label}</b>: <code>${pnl:+,.0f}</code> today | "
            f"<code>${cum:+,.0f}</code> cumulative | "
            f"<code>{ret:+.2f}%</code>"
        )

    winner = "Pre-Open" if pre_open["daily_pnl"] > pre_close["daily_pnl"] else "Pre-Close"
    diff = abs(pre_open["daily_pnl"] - pre_close["daily_pnl"])

    pos_lines = ""
    for p in pre_open.get("positions", [])[:8]:
        icon = "✅" if p["pnl_pct"] >= 0 else "❌"
        pos_lines += (
            f"\n{icon} <b>{p['ticker']}</b> "
            f"<code>{p['pnl_pct']:+.1f}%</code>"
        )

    return (
        f"<b>📊 EOD PNL — {trade_date}</b>\n\n"
        f"{fmt(pre_open, 'Pre-Open  ')}\n"
        f"{fmt(pre_close, 'Pre-Close ')}\n\n"
        f"🏆 <b>Winner: {winner}</b> (diff <code>${diff:,.0f}</code>)\n"
        f"{pos_lines}"
    )
