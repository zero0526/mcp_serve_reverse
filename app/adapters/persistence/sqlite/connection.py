from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.infrastructure.config.settings import settings


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# Ensure database directory exists
settings.database_dir.mkdir(parents=True, exist_ok=True)

# Sync engine & session maker (used by Alembic, CLI, sync utilities)
sync_engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

# Async engine & session maker (used by FastAPI / MCP runtime)
async_engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def get_sync_session() -> Generator[Session, None, None]:
    with SyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Tự động khởi tạo schema cơ sở dữ liệu nếu chưa tồn tại."""
    from sqlalchemy import text
    from app.adapters.persistence.sqlite.models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            res = await conn.execute(text("PRAGMA table_info(sessions)"))
            columns = [row[1] for row in res.fetchall()]
            if "task_id" not in columns:
                await conn.execute(text("ALTER TABLE sessions ADD COLUMN task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE"))
        except Exception:
            pass

