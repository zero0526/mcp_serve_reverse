from enum import Enum


class EventType(str, Enum):
    def __str__(self) -> str:
        return str(self.value)

    # JavaScript runtime
    FUNCTION_CALL = "function_call"
    FUNCTION_RETURN = "function_return"
    FUNCTION_THROW = "function_throw"

    # Network & Response Handling
    NETWORK_REQUEST = "network_request"
    NETWORK_RESPONSE = "network_response"
    NETWORK_FAILED = "network_failed"
    RESPONSE_CONSUMED = "response_consumed"
    RESPONSE_FIELD_READ = "response_field_read"

    # Cryptography
    CRYPTO_OPERATION = "crypto_operation"

    # Storage
    STORAGE_READ = "storage_read"
    STORAGE_WRITE = "storage_write"
    STORAGE_DELETE = "storage_delete"
    STORAGE_CLEAR = "storage_clear"

    # Serialization
    SERIALIZE = "serialize"
    DESERIALIZE = "deserialize"

    # Runtime & Console
    CONSOLE_LOG = "console_log"
    RUNTIME_ERROR = "runtime_error"

    # Browser lifecycle
    PAGE_CREATED = "page_created"
    PAGE_NAVIGATED = "page_navigated"
    PAGE_CLOSED = "page_closed"
