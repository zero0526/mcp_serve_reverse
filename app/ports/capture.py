from typing import Any, Protocol

from app.domain.trace.value_objects import PreSeedState


class BrowserCapturePort(Protocol):
    """Port điều khiển trình duyệt và thu thập sự kiện."""

    async def start(
        self,
        session_id: str,
        target: str | None = None,
        pre_seed_state: PreSeedState | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Khởi động browser session kèm pre-seed cookies / storage nếu có."""
        ...

    async def stop(self, session_id: str) -> None:
        """Dừng session và giải phóng tài nguyên."""
        ...

    async def get_status(self, session_id: str) -> dict[str, Any]:
        """Lấy trạng thái kết nối của adapter."""
        ...

    async def navigate(self, session_id: str, url: str) -> None:
        """Điều hướng page đến target URL."""
        ...
