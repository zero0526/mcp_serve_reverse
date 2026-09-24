import pytest
from app.adapters.persistence.sqlite.connection import async_engine
from app.adapters.persistence.sqlite.models import Base


@pytest.fixture(scope="session", autouse=True)
async def ensure_database_tables():
    """Tự động đảm bảo toàn bộ bảng trong SQLite được khởi tạo trước khi chạy test."""
    from sqlalchemy import text
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            res = await conn.execute(text("PRAGMA table_info(sessions)"))
            columns = [row[1] for row in res.fetchall()]
            if "task_id" not in columns:
                await conn.execute(text("ALTER TABLE sessions ADD COLUMN task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE"))
        except Exception:
            pass
    yield
