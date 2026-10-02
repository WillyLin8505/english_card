from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

engine = create_engine(config.database_url(), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def use_engine(url: str) -> None:
    """Point the app at another database (tests use lexicon_test)."""
    global engine
    engine.dispose()
    engine = create_engine(url, pool_pre_ping=True, future=True)
    SessionLocal.configure(bind=engine)


@contextmanager
def session_scope():
    s: Session = SessionLocal()
    try:
        yield s
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    with session_scope() as s:
        yield s
