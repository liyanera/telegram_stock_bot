"""
Paper trading MySQL schema and database operations.
"""
from __future__ import annotations
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, Text, Boolean, BigInteger
)
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from memory.mysql_memory import engine, Session, text


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    """Current portfolio state."""
    __tablename__ = "pt_portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), default="main")           # portfolio identifier
    cash = Column(Float, default=1_000_000.0)
    initial_capital = Column(Float, default=1_000_000.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Position(Base):
    """Current open positions."""
    __tablename__ = "pt_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_name = Column(String(50), default="main", index=True)
    ticker = Column(String(20), index=True)
    shares = Column(Float, default=0)
    avg_cost = Column(Float)                            # weighted average cost
    plan_type = Column(Enum("pre_open", "pre_close"))  # which plan opened this
    opened_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class RebalancingPlan(Base):
    """AI-generated rebalancing plans (stored for comparison)."""
    __tablename__ = "pt_rebalancing_plans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_date = Column(String(10), index=True)          # YYYY-MM-DD
    plan_type = Column(Enum("pre_open", "pre_close"), index=True)
    reasoning = Column(Text)                            # AI's full reasoning
    market_context = Column(Text)                       # macro/news context used
    created_at = Column(DateTime, default=datetime.utcnow)


class TradeOrder(Base):
    """Executed (simulated) trades."""
    __tablename__ = "pt_orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, index=True)               # links to RebalancingPlan
    plan_type = Column(Enum("pre_open", "pre_close"))
    trade_date = Column(String(10), index=True)
    ticker = Column(String(20))
    action = Column(Enum("BUY", "SELL"))
    shares = Column(Float)
    price_benchmark = Column(Enum("prev_close", "realtime", "open_vwap", "close_vwap", "vwap"))
    execution_price = Column(Float)                     # actual price used
    notional = Column(Float)                            # shares × price
    executed_at = Column(DateTime, default=datetime.utcnow)


class DailyPnl(Base):
    """Daily PNL records per plan type."""
    __tablename__ = "pt_daily_pnl"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), index=True)
    plan_type = Column(Enum("pre_open", "pre_close", "combined"))
    realized_pnl = Column(Float, default=0)
    unrealized_pnl = Column(Float, default=0)
    daily_pnl = Column(Float, default=0)               # realized + unrealized
    cumulative_pnl = Column(Float, default=0)
    portfolio_value = Column(Float)                    # cash + market value of positions
    gmv = Column(Float)                                # gross market value of positions
    turnover = Column(Float, default=0)                # today's trading notional
    weekly_turnover = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioSnapshot(Base):
    """End-of-day portfolio snapshots."""
    __tablename__ = "pt_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snap_date = Column(String(10), index=True)
    plan_type = Column(Enum("pre_open", "pre_close"))
    positions_json = Column(Text)                      # JSON snapshot of all positions
    portfolio_value = Column(Float)
    cash = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class TradingUniverse(Base):
    """User-managed AI trading universe — tickers + pillar classification."""
    __tablename__ = "trading_universe"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, index=True)
    pillar = Column(Enum("data_center", "memory", "energy", "photonics", "software", "other"))
    active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class TradingConfig(Base):
    """Runtime-configurable trading parameters."""
    __tablename__ = "trading_config"
    key = Column(String(50), primary_key=True)
    value = Column(String(200))
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


_DEFAULT_UNIVERSE = {
    "data_center": ["NVDA", "AMD", "AVGO", "ANET", "MRVL", "SMCI", "ARM", "MSFT", "GOOGL", "META", "AMZN"],
    "memory":      ["MU", "LRCX", "KLAC", "AMAT", "ASML"],
    "energy":      ["CEG", "VST", "TLN", "NEE", "NRG", "OKLO", "SMR"],
    "photonics":   ["COHR", "CIEN", "LITE", "VIAV", "FNSR", "IIVI"],
    "software":    ["PLTR", "CRWD", "NET", "DDOG", "NOW", "CRM"],
}

_DEFAULT_CONFIG = {
    "max_positions":           ("10",       "Max number of open positions"),
    "max_position_pct":        ("0.20",     "Max portfolio weight per position (0–1)"),
    "max_daily_turnover_pct":  ("0.10",     "Max daily turnover as fraction of GMV"),
    "max_weekly_turnover_pct": ("0.40",     "Max weekly turnover as fraction of GMV"),
    "min_trade_notional":      ("5000",     "Minimum trade size in USD"),
    "initial_capital":         ("1000000",  "Starting capital in USD"),
}


def init_trading_db():
    Base.metadata.create_all(engine)


# ── Portfolio operations ──────────────────────────────────────────────────────

def get_or_create_portfolio(name: str = "main") -> dict:
    with Session() as s:
        row = s.execute(
            text("SELECT id, cash, initial_capital FROM pt_portfolio WHERE name=:n"),
            {"n": name}
        ).first()
        if row:
            return {"name": name, "cash": row[1], "initial_capital": row[2]}
        s.add(Portfolio(name=name))
        s.commit()
        return {"name": name, "cash": 1_000_000.0, "initial_capital": 1_000_000.0}


def update_cash(name: str, cash: float):
    with Session() as s:
        s.execute(
            text("UPDATE pt_portfolio SET cash=:c, updated_at=NOW() WHERE name=:n"),
            {"c": cash, "n": name}
        )
        s.commit()


def get_positions(portfolio_name: str = "main") -> list:
    with Session() as s:
        rows = s.execute(
            text("SELECT ticker, shares, avg_cost, plan_type FROM pt_positions "
                 "WHERE portfolio_name=:p AND shares > 0 ORDER BY ticker"),
            {"p": portfolio_name}
        ).fetchall()
        return [{"ticker": r[0], "shares": r[1], "avg_cost": r[2], "plan_type": r[3]}
                for r in rows]


def upsert_position(portfolio_name: str, ticker: str, shares: float,
                    avg_cost: float, plan_type: str):
    with Session() as s:
        existing = s.execute(
            text("SELECT id, shares, avg_cost FROM pt_positions "
                 "WHERE portfolio_name=:p AND ticker=:t"),
            {"p": portfolio_name, "t": ticker}
        ).first()
        if existing:
            if shares <= 0:
                s.execute(
                    text("DELETE FROM pt_positions WHERE id=:id"),
                    {"id": existing[0]}
                )
            else:
                s.execute(
                    text("UPDATE pt_positions SET shares=:s, avg_cost=:c, "
                         "plan_type=:pt, updated_at=NOW() WHERE id=:id"),
                    {"s": shares, "c": avg_cost, "pt": plan_type, "id": existing[0]}
                )
        elif shares > 0:
            s.add(Position(
                portfolio_name=portfolio_name, ticker=ticker,
                shares=shares, avg_cost=avg_cost, plan_type=plan_type
            ))
        s.commit()


def get_weekly_turnover(trade_date: str) -> float:
    """Sum of notional traded in the past 5 trading days."""
    with Session() as s:
        row = s.execute(
            text("SELECT COALESCE(SUM(ABS(notional)), 0) FROM pt_orders "
                 "WHERE trade_date >= DATE_SUB(:d, INTERVAL 7 DAY)"),
            {"d": trade_date}
        ).first()
        return float(row[0]) if row else 0.0


def save_plan(plan_date: str, plan_type: str, reasoning: str, context: str) -> int:
    with Session() as s:
        p = RebalancingPlan(
            plan_date=plan_date, plan_type=plan_type,
            reasoning=reasoning, market_context=context
        )
        s.add(p)
        s.commit()
        return p.id


def save_order(plan_id: int, plan_type: str, trade_date: str, ticker: str,
               action: str, shares: float, price_benchmark: str,
               execution_price: float):
    notional = shares * execution_price
    with Session() as s:
        s.add(TradeOrder(
            plan_id=plan_id, plan_type=plan_type, trade_date=trade_date,
            ticker=ticker, action=action, shares=shares,
            price_benchmark=price_benchmark, execution_price=execution_price,
            notional=notional
        ))
        s.commit()


def save_daily_pnl(trade_date: str, plan_type: str, realized: float,
                   unrealized: float, cumulative: float, portfolio_value: float,
                   gmv: float, turnover: float, weekly_turnover: float):
    with Session() as s:
        s.add(DailyPnl(
            trade_date=trade_date, plan_type=plan_type,
            realized_pnl=realized, unrealized_pnl=unrealized,
            daily_pnl=realized + unrealized, cumulative_pnl=cumulative,
            portfolio_value=portfolio_value, gmv=gmv,
            turnover=turnover, weekly_turnover=weekly_turnover
        ))
        s.commit()


def get_cumulative_pnl(plan_type: str) -> float:
    with Session() as s:
        row = s.execute(
            text("SELECT COALESCE(SUM(daily_pnl), 0) FROM pt_daily_pnl "
                 "WHERE plan_type=:pt"),
            {"pt": plan_type}
        ).first()
        return float(row[0]) if row else 0.0


def get_pnl_history(plan_type: str, days: int = 30) -> list:
    with Session() as s:
        rows = s.execute(
            text("SELECT trade_date, daily_pnl, cumulative_pnl, portfolio_value, gmv "
                 "FROM pt_daily_pnl WHERE plan_type=:pt "
                 "ORDER BY trade_date DESC LIMIT :d"),
            {"pt": plan_type, "d": days}
        ).fetchall()
        return [{"date": r[0], "daily_pnl": r[1], "cumulative_pnl": r[2],
                 "portfolio_value": r[3], "gmv": r[4]}
                for r in reversed(rows)]


# ── Trading Universe ──────────────────────────────────────────────────────────

def seed_trading_tables():
    """Seed universe and config with defaults if tables are empty."""
    with Session() as s:
        count = s.execute(text("SELECT COUNT(*) FROM trading_universe")).scalar()
        if count == 0:
            for pillar, tickers in _DEFAULT_UNIVERSE.items():
                for ticker in tickers:
                    s.add(TradingUniverse(ticker=ticker, pillar=pillar))
            s.commit()

        count = s.execute(text("SELECT COUNT(*) FROM trading_config")).scalar()
        if count == 0:
            for key, (value, description) in _DEFAULT_CONFIG.items():
                s.add(TradingConfig(key=key, value=value, description=description))
            s.commit()


def get_universe() -> dict:
    """Returns {pillar: [tickers]} for all active tickers."""
    with Session() as s:
        rows = s.execute(
            text("SELECT ticker, pillar FROM trading_universe WHERE active=1 ORDER BY pillar, ticker")
        ).fetchall()
    result: dict[str, list] = {}
    for ticker, pillar in rows:
        result.setdefault(pillar, []).append(ticker)
    return result if result else _DEFAULT_UNIVERSE


def get_all_tickers() -> list:
    """Flat list of all active tickers in the universe."""
    universe = get_universe()
    return [t for tickers in universe.values() for t in tickers]


def add_to_universe(ticker: str, pillar: str, notes: str = "") -> bool:
    """Add or reactivate a ticker. Returns False if already active."""
    ticker = ticker.upper()
    with Session() as s:
        row = s.execute(
            text("SELECT id, active FROM trading_universe WHERE ticker=:t"),
            {"t": ticker}
        ).first()
        if row and row[1]:
            return False
        if row and not row[1]:
            s.execute(
                text("UPDATE trading_universe SET active=1, pillar=:p, notes=:n WHERE ticker=:t"),
                {"p": pillar, "n": notes, "t": ticker}
            )
        else:
            s.add(TradingUniverse(ticker=ticker, pillar=pillar, notes=notes))
        s.commit()
    return True


def remove_from_universe(ticker: str) -> bool:
    """Soft-delete a ticker. Returns False if not found."""
    ticker = ticker.upper()
    with Session() as s:
        row = s.execute(
            text("SELECT id FROM trading_universe WHERE ticker=:t AND active=1"),
            {"t": ticker}
        ).first()
        if not row:
            return False
        s.execute(
            text("UPDATE trading_universe SET active=0 WHERE ticker=:t"),
            {"t": ticker}
        )
        s.commit()
    return True


# ── Trading Config ────────────────────────────────────────────────────────────

def get_trading_config(key: str) -> str | None:
    """Get a config value as string. Returns None if not found."""
    with Session() as s:
        row = s.execute(
            text("SELECT value FROM trading_config WHERE key=:k"),
            {"k": key}
        ).first()
    return row[0] if row else None


def set_trading_config(key: str, value: str) -> bool:
    """Upsert a config value. Returns False if key is not a recognised parameter."""
    if key not in _DEFAULT_CONFIG:
        return False
    with Session() as s:
        row = s.execute(
            text("SELECT key FROM trading_config WHERE key=:k"), {"k": key}
        ).first()
        if row:
            s.execute(
                text("UPDATE trading_config SET value=:v, updated_at=NOW() WHERE key=:k"),
                {"v": str(value), "k": key}
            )
        else:
            desc = _DEFAULT_CONFIG[key][1]
            s.add(TradingConfig(key=key, value=str(value), description=desc))
        s.commit()
    return True


def get_all_trading_config() -> list:
    """Returns all config rows as [{key, value, description}]."""
    with Session() as s:
        rows = s.execute(
            text("SELECT key, value, description FROM trading_config ORDER BY key")
        ).fetchall()
    if rows:
        return [{"key": r[0], "value": r[1], "description": r[2]} for r in rows]
    return [{"key": k, "value": v, "description": d} for k, (v, d) in _DEFAULT_CONFIG.items()]
