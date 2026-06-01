from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text,
    Enum, DateTime, SmallInteger, Float, Boolean
)
from datetime import datetime
from typing import Optional
import config


engine = create_engine(config.MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    username = Column(String(100))
    first_name = Column(String(100))
    risk_tolerance = Column(Enum("conservative", "moderate", "aggressive"), default="moderate")
    created_at = Column(DateTime, default=datetime.utcnow)


class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True)
    ticker = Column(String(20))
    added_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True)
    role = Column(Enum("user", "assistant"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True)
    ticker = Column(String(20))
    query = Column(Text)
    response = Column(Text)
    feedback = Column(SmallInteger, default=0)  # 1=good, -1=bad, 0=none
    created_at = Column(DateTime, default=datetime.utcnow)


class StockThesis(Base):
    """Stores analysis theses with credibility tracking."""
    __tablename__ = "stock_theses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), index=True)
    thesis_type = Column(Enum("bull", "bear", "neutral"), default="neutral")
    thesis = Column(Text)                          # The recommendation reasoning
    credibility = Column(Float, default=0.5)       # 0.0 (wrong) to 1.0 (always right)
    confirmed_count = Column(Integer, default=0)   # Times price moved as predicted
    contradicted_count = Column(Integer, default=0)
    source = Column(String(100))                   # 'conversation', 'weekly_research', etc.
    chroma_doc_id = Column(String(200))            # Linked ChromaDB document ID
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceSnapshot(Base):
    """Weekly price snapshots for change detection."""
    __tablename__ = "price_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), index=True)
    price = Column(Float)
    snapped_at = Column(DateTime, default=datetime.utcnow, index=True)


def init_db():
    Base.metadata.create_all(engine)


# ── User ──────────────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> User:
    with Session() as session:
        user = session.get(User, user_id)
        if not user:
            user = User(id=user_id, username=username, first_name=first_name)
            session.add(user)
            session.commit()
            session.refresh(user)
        return user


def get_user(user_id: int) -> Optional[User]:
    with Session() as session:
        return session.get(User, user_id)


def update_risk_tolerance(user_id: int, level: str):
    with Session() as session:
        user = session.get(User, user_id)
        if user:
            user.risk_tolerance = level
            session.commit()


# ── Watchlist ─────────────────────────────────────────────────────────────────

def add_to_watchlist(user_id: int, ticker: str):
    ticker = ticker.upper()
    with Session() as session:
        exists = session.execute(
            text("SELECT id FROM watchlist WHERE user_id=:uid AND ticker=:t"),
            {"uid": user_id, "t": ticker},
        ).first()
        if not exists:
            session.add(Watchlist(user_id=user_id, ticker=ticker))
            session.commit()


def remove_from_watchlist(user_id: int, ticker: str):
    ticker = ticker.upper()
    with Session() as session:
        session.execute(
            text("DELETE FROM watchlist WHERE user_id=:uid AND ticker=:t"),
            {"uid": user_id, "t": ticker},
        )
        session.commit()


def get_watchlist(user_id: int) -> list:
    with Session() as session:
        rows = session.execute(
            text("SELECT ticker FROM watchlist WHERE user_id=:uid ORDER BY added_at"),
            {"uid": user_id},
        ).fetchall()
        return [r[0] for r in rows]


def get_all_monitored_tickers() -> list:
    """All unique tickers across all users' watchlists."""
    with Session() as session:
        rows = session.execute(
            text("SELECT DISTINCT ticker FROM watchlist ORDER BY ticker")
        ).fetchall()
        return [r[0] for r in rows]


# ── Conversations ─────────────────────────────────────────────────────────────

def save_conversation_turn(user_id: int, role: str, content: str):
    with Session() as session:
        session.add(Conversation(user_id=user_id, role=role, content=content))
        session.commit()


def get_recent_conversations(user_id: int, limit: int = 50) -> list:
    with Session() as session:
        rows = session.execute(
            text(
                "SELECT role, content, created_at FROM conversations "
                "WHERE user_id=:uid ORDER BY created_at DESC LIMIT :lim"
            ),
            {"uid": user_id, "lim": limit},
        ).fetchall()
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in reversed(rows)]


def save_analysis(user_id: int, ticker: str, query: str, response: str) -> int:
    with Session() as session:
        a = Analysis(user_id=user_id, ticker=ticker, query=query, response=response)
        session.add(a)
        session.commit()
        return a.id


def update_feedback(analysis_id: int, feedback: int):
    with Session() as session:
        session.execute(
            text("UPDATE analyses SET feedback=:f WHERE id=:id"),
            {"f": feedback, "id": analysis_id},
        )
        session.commit()


# ── Stock Theses ──────────────────────────────────────────────────────────────

def save_thesis(
    ticker: str,
    thesis: str,
    thesis_type: str = "bull",
    source: str = "conversation",
    chroma_doc_id: str = None,
) -> int:
    ticker = ticker.upper()
    with Session() as session:
        t = StockThesis(
            ticker=ticker,
            thesis=thesis,
            thesis_type=thesis_type,
            source=source,
            chroma_doc_id=chroma_doc_id,
        )
        session.add(t)
        session.commit()
        return t.id


def get_theses(ticker: str, active_only: bool = True) -> list:
    ticker = ticker.upper()
    with Session() as session:
        q = "SELECT id, thesis_type, thesis, credibility, confirmed_count, contradicted_count, source, created_at FROM stock_theses WHERE ticker=:t"
        if active_only:
            q += " AND active=1"
        q += " ORDER BY credibility DESC, created_at DESC"
        rows = session.execute(text(q), {"t": ticker}).fetchall()
        return [
            {
                "id": r[0], "thesis_type": r[1], "thesis": r[2],
                "credibility": r[3], "confirmed": r[4],
                "contradicted": r[5], "source": r[6], "created_at": r[7],
            }
            for r in rows
        ]


def update_thesis_credibility(thesis_id: int, consistent: bool):
    """
    consistent=True  → price moved as predicted → boost credibility
    consistent=False → price moved opposite     → reduce credibility
    """
    with Session() as session:
        row = session.execute(
            text("SELECT credibility, confirmed_count, contradicted_count FROM stock_theses WHERE id=:id"),
            {"id": thesis_id}
        ).first()
        if not row:
            return
        cred, confirmed, contradicted = row
        if consistent:
            cred = min(1.0, cred + 0.1)
            confirmed += 1
        else:
            cred = max(0.0, cred - 0.1)
            contradicted += 1
        session.execute(
            text(
                "UPDATE stock_theses SET credibility=:c, confirmed_count=:ok, "
                "contradicted_count=:bad, updated_at=NOW() WHERE id=:id"
            ),
            {"c": cred, "ok": confirmed, "bad": contradicted, "id": thesis_id},
        )
        session.commit()
        return cred


def get_high_credibility_theses(min_credibility: float = 0.7) -> list:
    with Session() as session:
        rows = session.execute(
            text(
                "SELECT ticker, thesis_type, thesis, credibility, source FROM stock_theses "
                "WHERE credibility >= :min AND active=1 ORDER BY credibility DESC LIMIT 50"
            ),
            {"min": min_credibility},
        ).fetchall()
        return [
            {"ticker": r[0], "thesis_type": r[1], "thesis": r[2],
             "credibility": r[3], "source": r[4]}
            for r in rows
        ]


# ── Price Snapshots ───────────────────────────────────────────────────────────

def save_price_snapshot(ticker: str, price: float):
    with Session() as session:
        session.add(PriceSnapshot(ticker=ticker.upper(), price=price))
        session.commit()


def get_last_snapshot(ticker: str) -> Optional[dict]:
    ticker = ticker.upper()
    with Session() as session:
        row = session.execute(
            text(
                "SELECT price, snapped_at FROM price_snapshots "
                "WHERE ticker=:t ORDER BY snapped_at DESC LIMIT 1"
            ),
            {"t": ticker},
        ).first()
        return {"price": row[0], "snapped_at": row[1]} if row else None
