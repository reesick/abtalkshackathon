"""
DB models — SQLAlchemy (async-compatible via sync session in threadpool).
Supports both SQLite (dev) and Postgres (prod) via DATABASE_URL env var.
"""
import os
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./abtalks.db")

# SQLite needs check_same_thread=False; Postgres ignores this kwarg
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)           # uuid
    persona_name = Column(String, nullable=False)
    persona_domain = Column(String, nullable=False)
    persona_json = Column(Text, nullable=False)     # full persona dict as JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False, index=True)
    tick_id = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    media_url = Column(String, nullable=True)
    media_type = Column(String, nullable=True)          # "video", "image", None
    content_type = Column(String, nullable=False)       # video_post / image_post / text_post
    topic_title = Column(String, nullable=True)
    topic_url = Column(String, nullable=True)
    topic_source = Column(String, nullable=True)
    rationale = Column(Text, nullable=True)             # JSON string
    sources = Column(Text, nullable=True)               # JSON array string
    created_at = Column(DateTime, nullable=False)


class TickLog(Base):
    __tablename__ = "tick_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False, index=True)
    tick_id = Column(String, nullable=False)
    tick_at = Column(DateTime, nullable=False)
    published = Column(Boolean, default=False)
    content_type = Column(String, nullable=True)
    error_msg = Column(Text, nullable=True)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    """Context manager — yields a SQLAlchemy Session, commits on exit, rolls back on error."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
