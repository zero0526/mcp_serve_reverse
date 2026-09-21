from typing import Any, Protocol

from app.domain.trace.value_objects import EventEnvelope


class EventStorePort(Protocol):
    """Port lưu trữ event store cho cả SQLite và raw file archive."""

    async def persist_event(
        self,
        event: EventEnvelope,
        normalized: dict[str, Any],
        raw_json: str | None = None,
    ) -> None:
        """Lưu một event vào store."""
        ...

    async def batch_persist_events(
        self,
        items: list[tuple[EventEnvelope, dict[str, Any]]],
    ) -> None:
        """Lưu batch events."""
        ...
