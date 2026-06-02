import re
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest
from memory import mysql_memory, redis_memory
from claude.client import chat


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if not message or not message.text:
        return

    bot_username = context.bot.username
    chat_type = message.chat.type
    text = message.text

    # In groups: only respond when @mentioned or replying to bot
    if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_mention = f"@{bot_username}" in text
        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == context.bot.id
        )
        if not is_mention and not is_reply_to_bot:
            return
        text = text.replace(f"@{bot_username}", "").strip()
        if not text:
            await message.reply_text("Yes? Ask me anything about stocks!")
            return

    mysql_memory.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await message.chat.send_action(ChatAction.TYPING)

    try:
        reply = await _run_chat(user.id, text)
    except Exception as e:
        reply = f"Sorry, something went wrong: {e}"

    for chunk in _split_message(reply):
        await _send_html(message, chunk)


async def _run_chat(user_id: int, text: str) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, chat, user_id, text)


async def _send_html(message, text: str):
    """Send with HTML parse mode; fall back to plain text if HTML is malformed."""
    try:
        await message.reply_text(text, parse_mode="HTML")
    except BadRequest:
        # Strip all HTML tags and send as plain text fallback
        plain = re.sub(r'<[^>]+>', '', text)
        await message.reply_text(plain, parse_mode=None)


def _split_message(text: str, max_len: int = 4000) -> list:
    """Split long messages, keeping HTML tags intact where possible."""
    if len(text) <= max_len:
        return [text]

    parts = []
    while len(text) > max_len:
        # Try to split at a paragraph break near the limit
        split_at = text.rfind('\n\n', 0, max_len)
        if split_at == -1:
            split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()

    if text:
        parts.append(text)
    return parts
