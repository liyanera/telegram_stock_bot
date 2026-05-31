from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import Column, BigInteger, Integer, String, Text, Enum, DateTime, SmallInteger
from datetime import datetime
from typing import Optional
import config


engine = create_engine(config.MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)  # Telegram user ID
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


def init_db():
    Base.metadata.create_all(engine)


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
