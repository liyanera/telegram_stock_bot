from __future__ import annotations

import json
import redis
import config
from typing import Optional

_client: Optional[redis.Redis] = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            decode_responses=True,
        )
    return _client


def _key(user_id: int) -> str:
    return f"conv:{user_id}"


def get_history(user_id: int) -> list[dict]:
    raw = get_client().get(_key(user_id))
    if not raw:
        return []
    return json.loads(raw)


def append_turn(user_id: int, role: str, content: str):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    # Keep only last N turns (each turn = 1 message)
    max_turns = config.MAX_CONVERSATION_TURNS
    if len(history) > max_turns:
        history = history[-max_turns:]
    get_client().set(_key(user_id), json.dumps(history), ex=86400 * 7)  # 7-day TTL


def clear_history(user_id: int):
    get_client().delete(_key(user_id))


def ping() -> bool:
    try:
        return get_client().ping()
    except Exception:
        return False
