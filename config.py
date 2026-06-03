from dotenv import load_dotenv
import os
import re

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", 20))
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
TRADING_GROUP_CHAT_ID = os.getenv("TRADING_GROUP_CHAT_ID", "")
DISABLE_SCHEDULER = os.getenv("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes")

# MySQL — accept Railway's MYSQL_URL or individual vars
_mysql_url = os.getenv("MYSQL_URL") or os.getenv("DATABASE_URL")
if _mysql_url:
    # Ensure SQLAlchemy driver prefix
    MYSQL_URL = re.sub(r"^mysql://", "mysql+pymysql://", _mysql_url)
else:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "stockbot")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "stockbot")
    MYSQL_URL = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    )

# Redis — accept Railway's REDIS_URL or individual vars
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
REDIS_HOST = os.getenv("REDISHOST", os.getenv("REDIS_HOST", "localhost"))
REDIS_PORT = int(os.getenv("REDISPORT", os.getenv("REDIS_PORT", 6379)))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or os.getenv("REDISPASSWORD") or None
