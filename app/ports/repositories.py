from typing import Any, Protocol

from app.domain.shared.enums import SessionStatus
from app.domain.trace.value_objects import EventEnvelope


class SessionRepositoryPort(Protocol):
    """Port truy xuất và cập nhật sessions."""

    async def create(
        self,
        session_id: str,
        name: str | None,
        target: str | None,
        source: str = "browser",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def update_status(
        self,
        session_id: str,
        status: SessionStatus | str,
        ended_at_ns: int | None = None,
        metadata_update: dict[str, Any] | None = None,
    ) -> None:
        ...

    async def get_by_id(self, session_id: str) -> dict[str, Any] | None:
        ...

    async def get_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        ...

    async def get_statistics(self, session_id: str) -> dict[str, int]:
        ...


class EventRepositoryPort(Protocol):
    """Port lưu và truy vấn trace events cùng các thực thể quan hệ mạng/storage."""

    async def save_trace_event(self, event: EventEnvelope) -> None:
        ...

    async def save_network_request(self, request_data: dict[str, Any]) -> None:
        ...

    async def save_network_response(self, response_data: dict[str, Any]) -> None:
        ...

    async def save_storage_operation(self, op_data: dict[str, Any]) -> None:
        ...

    async def search_events(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        ...
