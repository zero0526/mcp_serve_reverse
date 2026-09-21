from app.domain.trace.value_objects import EventEnvelope


class EventValidator:
    """Kiểm tra tính hợp lệ của EventEnvelope."""

    def validate(self, event: EventEnvelope) -> None:
        if not event.session_id or not event.session_id.strip():
            raise ValueError("session_id is required and cannot be empty")

        if not event.event_id or not event.event_id.strip():
            raise ValueError("event_id is required and cannot be empty")

        if event.timestamp_ns <= 0:
            raise ValueError(f"Invalid timestamp_ns: {event.timestamp_ns}")

        if not event.event_type:
            raise ValueError("event_type cannot be empty")


event_validator = EventValidator()
