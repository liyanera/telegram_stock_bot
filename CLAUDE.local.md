# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Local development
source venv/bin/activate
python main.py

# Run a specific scheduled script manually
python scripts/trading_preopen.py
python scripts/trading_preclose.py
python scripts/trading_eod.py
python scripts/daily_premarket.py
python scripts/weekly_research.py
python scripts/weekly_monitor.py
```

**Important**: Only one bot process should run at a time. Telegram uses polling, so two processes (local + Railway) will conflict and cause updates to be missed or duplicated. Stop the local bot before deploying to Railway.

## Environment Setup

Copy `.env.example` to `.env`. Required vars:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ANTHROPIC_API_KEY`
- MySQL: `MYSQL_URL` (Railway format) or individual `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`
- Redis: `REDIS_URL` or `REDIS_HOST/PORT/PASSWORD`
- `NEWS_API_KEY` — from newsapi.org
- `TRADING_GROUP_CHAT_ID` — Telegram group chat ID for paper trading notifications (optional)

## Deployment

Deployed on Railway via Dockerfile. Push to `main` triggers redeploy. Config in `railway.toml`.

## Architecture

### Core Loop

`main.py` wires together three subsystems:
1. **Telegram bot** (python-telegram-bot) — handles user messages and commands
2. **APScheduler** — runs scheduled scripts (pre-market, trading, weekly)
3. **Knowledge base seeding** — on startup, chunks all `knowledge/*.md` and `knowledge/*.txt` files into ChromaDB

### Memory (Three-Layer)

| Layer | Storage | Purpose |
|-------|---------|---------|
| Short-term | Redis | Per-user conversation history (last 20 turns, 7-day TTL) |
| Long-term | MySQL | Users, watchlists, conversation logs, stock theses with credibility |
| Semantic | ChromaDB (`chroma_db/`) | Vector search over knowledge files + AI-generated theses |

`memory/mysql_memory.py` — SQLAlchemy models and all DB operations. Key table: `stock_theses` tracks bull/bear theses with a `credibility` float (0.0–1.0) that increases/decreases as weekly monitoring validates or contradicts them.

### Chat Flow (`claude/client.py:chat`)

1. Build system prompt: static persona (prompt-cached) + dynamic context (user profile + RAG results)
2. Agentic tool-use loop with Claude Sonnet until `stop_reason != "tool_use"`
3. Post-response: Claude Haiku extracts any stock theses mentioned and persists them to MySQL + ChromaDB
4. Skip memory persistence entirely for casual messages (short texts with no stock keywords)

The static persona in `claude/prompts.py` uses `cache_control: ephemeral` to reduce API costs — the large static section is cached for 5 minutes.

### Claude Tools (`claude/tools.py` + `claude/client.py:_dispatch_tool`)

Eight tools available to the chat agent:
- `get_stock_price`, `get_financials`, `get_technical_indicators`, `get_analyst_ratings` — yfinance
- `get_stock_news`, `get_enriched_news` — NewsAPI + Haiku sentiment synthesis
- `get_recommendations` — queries MySQL theses; falls back to `_discover_fresh_picks` if DB is empty
- `search_knowledge_base` — ChromaDB semantic search

### Paper Trading System (`trading/`)

Runs on a $1M simulated portfolio focused on AI industry stocks across 5 pillars (data center, memory, energy, photonics, software). The universe is defined in `trading/agent.py:UNIVERSE`.

**Daily schedule (UTC)**:
- 13:20 — Pre-open rebalancing (`scripts/trading_preopen.py`) — fundamental/macro-driven, uses prev-close prices
- 19:30 — Pre-close refinement (`scripts/trading_preclose.py`) — momentum-driven, uses realtime prices
- 21:00 — EOD PNL calculation (`scripts/trading_eod.py`)

**Flow**: `scripts/trading_preopen.py` → `trading/agent.py:generate_rebalancing_plan` (Claude Sonnet generates JSON trades) → `trading/constraints.py:validate_plan` → `trading/executor.py:execute_plan` → MySQL + Telegram group notification.

Trading DB tables are prefixed `pt_` (`pt_portfolio`, `pt_positions`, `pt_orders`, `pt_daily_pnl`, `pt_snapshots`, `pt_rebalancing_plans`) and are separate from the chat memory tables.

### Scheduled Research (`scripts/`)

- `weekly_research.py` — Monday 08:00 UTC: screens full market universe, uses Haiku to identify top picks, saves theses
- `weekly_monitor.py` — Monday 09:00 UTC: checks if existing theses were validated by price movements, updates credibility scores
- `daily_premarket.py` — Mon-Fri 13:00 UTC: fetches news for watchlist tickers + macro summary, sends to Telegram

### Telegram Formatting

All bot responses use **HTML parse mode only** — no markdown. The static persona enforces this. Format rules: `<b>` for headers/tickers, `<code>` for numbers/prices, `<i>` for disclaimers, `<pre>` for tables. Messages over 4000 chars are split at paragraph boundaries (`bot/handlers.py:_split_message`).

## Key Design Decisions

- **Model routing**: Claude Sonnet for chat and trading agent (quality), Claude Haiku for extraction tasks (speed/cost): thesis extraction, news sentiment, stock discovery
- **Credibility system**: theses start at 0.5, gain/lose 0.1 per weekly validation, capped [0.0, 1.0]. ChromaDB search re-ranks by `similarity * (0.6 + 0.4 * credibility)`.
- **100% invested mandate**: the trading agent is instructed to deploy all cash; residual cash > $5k triggers more trades
- **In-group behavior**: the message handler only responds to @mentions or direct replies in group chats, never to all group messages
