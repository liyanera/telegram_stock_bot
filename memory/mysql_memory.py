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


def get_all_theses_ranked(
    thesis_type: str = "bull",
    min_credibility: float = 0.0,
    limit: int = 10,
) -> list:
    """Return theses ranked by credibility, for use in recommendations tool."""
    with Session() as session:
        type_filter = "" if thesis_type == "all" else "AND thesis_type=:tt"
        rows = session.execute(
            text(
                f"SELECT ticker, thesis_type, thesis, credibility, "
                f"confirmed_count, contradicted_count, source, created_at "
                f"FROM stock_theses "
                f"WHERE active=1 AND credibility >= :mc {type_filter} "
                f"ORDER BY credibility DESC, confirmed_count DESC "
                f"LIMIT :lim"
            ),
            {"mc": min_credibility, "tt": thesis_type, "lim": limit},
        ).fetchall()
        return [
            {
                "ticker": r[0],
                "thesis_type": r[1],
                "thesis": r[2],
                "credibility": round(r[3], 2),
                "confirmed_count": r[4],
                "contradicted_count": r[5],
                "source": r[6],
                "added": str(r[7])[:10],
            }
            for r in rows
        ]


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


# ── Earnings Memory ───────────────────────────────────────────────────────────

class EarningsMemory(Base):
    """Per-quarter earnings snapshots for pattern recognition."""
    __tablename__ = "stock_earnings_memory"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), index=True)
    quarter = Column(String(10))               # e.g. "2026Q1"
    report_date = Column(String(10))           # "YYYY-MM-DD"
    eps_actual = Column(Float, nullable=True)
    eps_estimate = Column(Float, nullable=True)
    eps_surprise_pct = Column(Float, nullable=True)
    revenue_b = Column(Float, nullable=True)   # in billions
    revenue_growth_yoy = Column(Float, nullable=True)
    gross_margin = Column(Float, nullable=True)
    profit_margin = Column(Float, nullable=True)
    free_cash_flow_b = Column(Float, nullable=True)
    analyst_target = Column(Float, nullable=True)
    recommendation = Column(String(20), nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)


def get_last_earnings_quarter(ticker: str) -> Optional[str]:
    ticker = ticker.upper()
    with Session() as session:
        row = session.execute(
            text("SELECT quarter FROM stock_earnings_memory "
                 "WHERE ticker=:t ORDER BY saved_at DESC LIMIT 1"),
            {"t": ticker},
        ).first()
    return row[0] if row else None


def save_earnings_snapshot(ticker: str, quarter: str, data: dict) -> int:
    ticker = ticker.upper()
    rev = data.get("revenue")
    fcf = data.get("free_cash_flow")
    with Session() as session:
        row = session.execute(
            text("SELECT id FROM stock_earnings_memory WHERE ticker=:t AND quarter=:q"),
            {"t": ticker, "q": quarter},
        ).first()
        if row:
            return row[0]  # already saved this quarter
        entry = EarningsMemory(
            ticker=ticker,
            quarter=quarter,
            report_date=datetime.utcnow().strftime("%Y-%m-%d"),
            eps_actual=data.get("eps"),
            eps_estimate=data.get("eps_estimate"),
            eps_surprise_pct=data.get("eps_surprise_pct"),
            revenue_b=round(rev / 1e9, 3) if rev else None,
            revenue_growth_yoy=data.get("revenue_growth"),
            gross_margin=data.get("gross_margin"),
            profit_margin=data.get("profit_margin"),
            free_cash_flow_b=round(fcf / 1e9, 3) if fcf else None,
            analyst_target=data.get("analyst_target_price"),
            recommendation=data.get("recommendation"),
        )
        session.add(entry)
        session.commit()
        return entry.id


def get_earnings_history(ticker: str, limit: int = 8) -> list:
    ticker = ticker.upper()
    with Session() as session:
        rows = session.execute(
            text("SELECT quarter, report_date, eps_actual, eps_estimate, eps_surprise_pct, "
                 "revenue_b, revenue_growth_yoy, gross_margin, profit_margin, "
                 "free_cash_flow_b, analyst_target, recommendation "
                 "FROM stock_earnings_memory WHERE ticker=:t "
                 "ORDER BY quarter DESC LIMIT :lim"),
            {"t": ticker, "lim": limit},
        ).fetchall()
    return [
        {
            "quarter": r[0], "report_date": r[1],
            "eps_actual": r[2], "eps_estimate": r[3], "eps_surprise_pct": r[4],
            "revenue_b": r[5], "revenue_growth_yoy": r[6],
            "gross_margin": r[7], "profit_margin": r[8],
            "free_cash_flow_b": r[9], "analyst_target": r[10], "recommendation": r[11],
        }
        for r in rows
    ]


# ── News Themes ───────────────────────────────────────────────────────────────

class NewsTheme(Base):
    """Rolling news theme accumulation per ticker."""
    __tablename__ = "stock_news_themes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), index=True)
    date = Column(String(10))
    sentiment = Column(String(20))
    score = Column(Float)
    themes = Column(Text)     # JSON list
    catalysts = Column(Text)  # JSON list
    saved_at = Column(DateTime, default=datetime.utcnow)


def save_news_theme(ticker: str, date: str, sentiment: str, score: float,
                    themes: list, catalysts: list):
    import json
    ticker = ticker.upper()
    with Session() as session:
        session.add(NewsTheme(
            ticker=ticker, date=date, sentiment=sentiment, score=score,
            themes=json.dumps(themes), catalysts=json.dumps(catalysts),
        ))
        session.commit()


def get_news_theme_history(ticker: str, limit: int = 12) -> list:
    import json
    ticker = ticker.upper()
    with Session() as session:
        rows = session.execute(
            text("SELECT date, sentiment, score, themes, catalysts "
                 "FROM stock_news_themes WHERE ticker=:t "
                 "ORDER BY date DESC LIMIT :lim"),
            {"t": ticker, "lim": limit},
        ).fetchall()
    return [
        {
            "date": r[0], "sentiment": r[1], "score": r[2],
            "themes": json.loads(r[3] or "[]"),
            "catalysts": json.loads(r[4] or "[]"),
        }
        for r in rows
    ]
