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
    text = Column(Text, nullable=False)                 # primary/default text (Hinglish, per current voice)
    text_en = Column(Text, nullable=True)                # plain-English variant, for the EN/HI toggle
    text_hi = Column(Text, nullable=True)                # Hinglish variant (usually == text today)
    media_url = Column(String, nullable=True)
    media_type = Column(String, nullable=True)          # "meme", "image", "video", None
    content_type = Column(String, nullable=False)       # meme_post / text_post
    topic_title = Column(String, nullable=True)
    topic_url = Column(String, nullable=True)
    topic_source = Column(String, nullable=True)
    rationale = Column(Text, nullable=True)             # JSON string — editorial judge's rationale
    sources = Column(Text, nullable=True)               # JSON array string
    meme_judge_json = Column(Text, nullable=True)        # JSON — meme humour judge's score/reasoning, if content_type == meme_post
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


class MemeTemplate(Base):
    """
    Persistent meme-template registry (meme spec section 8). Semantic
    metadata is enriched separately/infrequently (section 74) and preserved
    across sync runs (section 73) — sync never wipes semantic_json,
    times_used, or last_used_at.
    """
    __tablename__ = "meme_templates"

    id = Column(String, primary_key=True)             # f"{provider}:{provider_template_id}"
    provider = Column(String, nullable=False, default="imgflip")
    provider_template_id = Column(String, nullable=False, index=True)

    name = Column(String, nullable=False)
    image_url = Column(String, nullable=False)

    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    box_count = Column(Integer, nullable=True)

    # Semantic enrichment (section 9, 11) — JSON strings; None until enriched.
    semantic_format = Column(String, nullable=True)      # e.g. "comparison", "underreaction"
    template_family = Column(String, nullable=True)      # section 38 — coarser than semantic_format
    visual_grammar_json = Column(Text, nullable=True)
    humour_mechanisms_json = Column(Text, nullable=True)  # JSON list
    best_for_json = Column(Text, nullable=True)           # JSON list
    bad_for_json = Column(Text, nullable=True)            # JSON list
    caption_structure_json = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=True)

    popularity_score = Column(Integer, nullable=False, default=0)  # rank order from get_memes
    freshness_score = Column(Integer, nullable=False, default=50)  # 0-100, starts neutral

    times_selected = Column(Integer, nullable=False, default=0)
    times_rendered = Column(Integer, nullable=False, default=0)
    times_posted = Column(Integer, nullable=False, default=0)

    last_used_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)

    average_humour_score = Column(Integer, nullable=True)
    average_engagement_score = Column(Integer, nullable=True)

    active = Column(Boolean, nullable=False, default=True)
    health = Column(String, nullable=False, default="active")  # active/inactive/broken/stale/unsafe

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MemeUsage(Base):
    """Per-post meme usage record (meme spec section 40)."""
    __tablename__ = "meme_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False, index=True)
    post_id = Column(Integer, nullable=True)

    template_id = Column(String, nullable=False, index=True)
    template_family = Column(String, nullable=True)

    humour_mechanism = Column(String, nullable=True)

    topic_title = Column(String, nullable=True)
    topic_source = Column(String, nullable=True)

    caption_json = Column(Text, nullable=True)   # JSON list of text_boxes
    humour_score = Column(Integer, nullable=True)
    judge_score_json = Column(Text, nullable=True)

    published_at = Column(DateTime, nullable=True)
    engagement_json = Column(Text, nullable=True)  # filled in later if performance data becomes available

    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite schema migration for newly added columns
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            columns = [row[1] for row in conn.execute(text("PRAGMA table_info(posts)")).fetchall()]
            if "text_en" not in columns:
                conn.execute(text("ALTER TABLE posts ADD COLUMN text_en TEXT"))
            if "text_hi" not in columns:
                conn.execute(text("ALTER TABLE posts ADD COLUMN text_hi TEXT"))
            if "meme_judge_json" not in columns:
                conn.execute(text("ALTER TABLE posts ADD COLUMN meme_judge_json TEXT"))
            conn.commit()
    except Exception:
        pass



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
