import datetime
import json
from typing import Any


class SafeJSONEncoder(json.JSONEncoder):
    """Encoder hỗ trợ các kiểu dữ liệu nâng cao như datetime, bytes, sets."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        if isinstance(o, set):
            return list(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return super().default(o)


def safe_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=SafeJSONEncoder, ensure_ascii=False)


def safe_loads(s: str) -> Any:
    return json.loads(s)
