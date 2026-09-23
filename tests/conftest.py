import pytest
from app.adapters.persistence.sqlite.connection import async_engine
from app.adapters.persistence.sqlite.models import Base


@pytest.fixture(scope="session", autouse=True)
async def ensure_database_tables():
    """Tự động đảm bảo toàn bộ bảng trong SQLite được khởi tạo trước khi chạy test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
