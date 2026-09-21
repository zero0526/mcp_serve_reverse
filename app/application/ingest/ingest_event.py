from app.application.ingest.normalize_event import EventNormalizer, event_normalizer
from app.application.ingest.validate_event import EventValidator, event_validator
from app.domain.trace.value_objects import EventEnvelope
from app.infrastructure.serialization.redaction import RedactionEngine, redaction_engine
from app.ports.event_store import EventStorePort


class IngestEventUseCase:
    """Use case xử lý chuỗi ingestion: Validate -> Redact -> Normalize -> Persist."""

    def __init__(
        self,
        event_store: EventStorePort,
        validator: EventValidator = event_validator,
        normalizer: EventNormalizer = event_normalizer,
        redactor: RedactionEngine = redaction_engine,
    ):
        self.event_store = event_store
        self.validator = validator
        self.normalizer = normalizer
        self.redactor = redactor

    async def execute(self, event: EventEnvelope) -> None:
        # 1. Validate
        self.validator.validate(event)

        # 2. Redact sensitive fields
        redacted_payload = self.redactor.redact_payload(str(event.event_type), event.payload)
        event.payload = redacted_payload

        # 3. Normalize
        normalized = self.normalizer.normalize(event)

        # 4. Persist to store
        await self.event_store.persist_event(event, normalized)
