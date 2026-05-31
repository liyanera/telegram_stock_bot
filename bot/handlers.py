from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ChatType
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

    # In groups: only respond when @mentioned or when replying to bot's message
    if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_mention = f"@{bot_username}" in text
        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == context.bot.id
        )
        if not is_mention and not is_reply_to_bot:
            return

        # Strip the @mention from the query before sending to Claude
        text = text.replace(f"@{bot_username}", "").strip()
        if not text:
            await message.reply_text("Yes? Ask me anything about stocks!")
            return

    # Ensure user exists in DB
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
        await message.reply_text(chunk, parse_mode=None)


async def _run_chat(user_id: int, text: str) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, chat, user_id, text)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        parts.append(text[:max_len])
        text = text[max_len:]
    return parts
