"""Quản lý dependency injection container cho Playground Backend."""

from app.bootstrap import ApplicationContainer, bootstrap_container

_container: ApplicationContainer | None = None


async def get_container() -> ApplicationContainer:
    """Lấy hoặc khởi tạo ApplicationContainer singleton."""
    global _container
    if _container is None:
        _container = bootstrap_container()
        await _container.initialize()
    return _container
