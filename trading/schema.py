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
