import datetime
import json
import re
from typing import Any
from urllib.parse import parse_qsl, unquote


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


_ANTI_HIJACK_PREFIXES = (
    "for (;;);",
    "while(1);",
    ")]}',",
    ")]}'",
    "/*-secure-*/",
    "<!--",
)

_VALID_PARAM_KEY_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\$\[\]%:]+$")


def _is_valid_param_key(k: str) -> bool:
    if not k or len(k) > 100:
        return False
    return bool(_VALID_PARAM_KEY_REGEX.match(k))


def _strip_anti_hijack_prefix(s: str) -> str:
    s_strip = s.strip()
    for prefix in _ANTI_HIJACK_PREFIXES:
        if s_strip.startswith(prefix):
            return s_strip[len(prefix):].strip()
    return s_strip


def _try_parse_json(s: str) -> Any:
    """Thử parse chuỗi JSON (object, array, URL-encoded JSON, hoặc NDJSON nhiều dòng)."""
    clean_s = _strip_anti_hijack_prefix(s)

    # Nếu chuỗi bị url-encode thuần (bắt đầu bằng %7B / %5B)
    if clean_s.startswith(("%7B", "%7b", "%5B", "%5b")):
        try:
            unquoted = unquote(clean_s).strip()
            if (unquoted.startswith("{") and unquoted.endswith("}")) or (unquoted.startswith("[") and unquoted.endswith("]")):
                return json.loads(unquoted)
        except Exception:
            pass

    # 1. Thử parse nếu là JSON Object hoặc Array chuẩn
    if (clean_s.startswith("{") and clean_s.endswith("}")) or (clean_s.startswith("[") and clean_s.endswith("]")):
        try:
            return json.loads(clean_s)
        except Exception:
            pass

    # 2. Thử NDJSON / streaming responses nhiều dòng (ví dụ Facebook Comet BigPipe)
    if "\n" in clean_s:
        lines = [line.strip() for line in clean_s.split("\n") if line.strip()]
        if len(lines) > 1:
            parsed_lines = []
            all_valid = True
            for line in lines:
                line_clean = _strip_anti_hijack_prefix(line)
                if (line_clean.startswith("{") and line_clean.endswith("}")) or (line_clean.startswith("[") and line_clean.endswith("]")):
                    try:
                        parsed_lines.append(json.loads(line_clean))
                    except Exception:
                        all_valid = False
                        break
                else:
                    all_valid = False
                    break
            if all_valid and parsed_lines:
                return parsed_lines

    return None


def _try_parse_form_urlencoded(s: str) -> dict[str, Any] | None:
    """Thử parse chuỗi form-urlencoded có chứa tham số thông thường hoặc JSON lồng nhau."""
    if not isinstance(s, str) or "=" not in s:
        return None
    # Tránh parse nhầm các format khác như JSON, HTML, XML, Markdown
    s_stripped = s.strip()
    if s_stripped.startswith(("{", "[", "<", "#", "/*", "--")):
        return None
    if "\n" in s_stripped or "\r" in s_stripped:
        return None

    try:
        pairs = parse_qsl(s_stripped, keep_blank_values=True)
        if not pairs:
            return None

        # Kiểm tra tính hợp lệ của tất cả các param keys
        if not all(_is_valid_param_key(k) for k, _ in pairs):
            return None

        # Nếu chỉ có duy nhất 1 param (không có dấu '&'), chỉ chấp nhận nếu value có dạng JSON
        if len(pairs) == 1:
            _, v = pairs[0]
            v_strip = v.strip()
            if not (
                v_strip.startswith(("{", "[", "%7B", "%5B", "%7b", "%5b"))
                or (v_strip.startswith('"') and v_strip.endswith('"'))
            ):
                return None

        result: dict[str, Any] = {}
        for k, v in pairs:
            if k in result:
                if isinstance(result[k], list):
                    result[k].append(v)
                else:
                    result[k] = [result[k], v]
            else:
                result[k] = v
        return result
    except Exception:
        return None


def parse_smart_payload(data: Any, max_depth: int = 5) -> Any:
    """Tự động phân tích và chuyển đổi payload (form-urlencoded, nested JSON, NDJSON) thành cấu trúc dict/list.

    Giải quyết triệt để:
    - Body dạng form-urlencoded chứa chuỗi JSON lồng nhau (như Facebook GraphQL `variables=%7B...%7D`).
    - Response JSON chứa tiền tố bảo vệ CSRF (`for (;;);`).
    - Các trường bên trong dict/list chứa chuỗi JSON lồng (như `errors[0]['description']`).
    - Giảm thiểu tối đa tiêu tốn Context Token cho LLM Agent.
    """
    if max_depth <= 0 or data is None:
        return data

    if isinstance(data, (int, float, bool)):
        return data

    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8", errors="replace")
        except Exception:
            return data

    if isinstance(data, list):
        return [parse_smart_payload(item, max_depth=max_depth - 1) for item in data]

    if isinstance(data, dict):
        return {k: parse_smart_payload(v, max_depth=max_depth - 1) for k, v in data.items()}

    if isinstance(data, str):
        # 1. Thử parse form-urlencoded trước (vì form-urlencoded có thể chứa key=value mà value là json)
        form_dict = _try_parse_form_urlencoded(data)
        if form_dict is not None:
            return parse_smart_payload(form_dict, max_depth=max_depth - 1)

        # 2. Thử parse JSON (Object, Array, NDJSON, URL-encoded JSON)
        json_val = _try_parse_json(data)
        if json_val is not None:
            return parse_smart_payload(json_val, max_depth=max_depth - 1)

    return data

