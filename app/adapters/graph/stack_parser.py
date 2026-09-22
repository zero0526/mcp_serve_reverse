import re
from pydantic import BaseModel


class StackFrame(BaseModel):
    """Đại diện cho một khung thực thi (Call Frame) trích xuất từ Call Stack."""

    function_name: str
    file_url: str
    line_no: int | None = None
    col_no: int | None = None
    raw_frame: str


# Regex nhận diện định dạng V8 stack frames
FRAME_REGEX = re.compile(
    r"^\s*at\s+(?:(?P<async>async)\s+)?(?:(?P<func>[^\s(]+)\s+)?\(?(?P<loc>[^)]+)\)?$"
)
INTERNAL_KEYWORDS = [
    "api_lineage",
    "__api_lineage",
    "fetch.js",
    "xhr.js",
    "storage.js",
    "crypto.js",
    "cookie.js",
    "window.fetch",
    "Response.json",
    "Response.text",
    "Storage.setItem",
    "Storage.getItem",
    "Storage.removeItem",
    "Storage.clear",
    "BindingsController",
    "callBinding",
    "_global.<computed>",
    "Object.get",
    "wrapWithLineageProxy",
    "emitBridgeEvent",
]


def parse_v8_stack(stack_str: str | None) -> list[StackFrame]:
    """Phân tách chuỗi Call Stack V8 thành danh sách các StackFrame có cấu trúc.

    Lọc bỏ các frame nội bộ của instrumentation để chỉ giữ lại mã nguồn ứng dụng.
    """
    if not stack_str:
        return []

    frames: list[StackFrame] = []
    lines = stack_str.splitlines()

    for line in lines:
        line_clean = line.strip()
        if not line_clean.startswith("at "):
            continue

        # Kiểm tra lọc các frame nội bộ
        if any(keyword in line_clean for keyword in INTERNAL_KEYWORDS):
            continue

        rest = line_clean[3:].strip()
        if rest.startswith("async "):
            rest = rest[6:].strip()

        if "(" in rest and rest.endswith(")"):
            first_paren = rest.find("(")
            func_name = rest[:first_paren].strip()
            loc = rest[first_paren + 1 : -1].strip()
        else:
            func_name = "<anonymous>"
            loc = rest

        if func_name.startswith("new "):
            func_name = func_name[4:].strip()
        if not func_name:
            func_name = "<anonymous>"

        if any(keyword == func_name for keyword in INTERNAL_KEYWORDS):
            continue

        file_url = loc
        line_no = None
        col_no = None

        parts = loc.rsplit(":", 2)
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            file_url = parts[0]
            line_no = int(parts[1])
            col_no = int(parts[2])
        elif len(parts) == 2 and parts[1].isdigit():
            file_url = parts[0]
            line_no = int(parts[1])

        if ", " in file_url:
            file_url = file_url.split(", ")[-1]
        if file_url.startswith("("):
            file_url = file_url[1:]

        frames.append(
            StackFrame(
                function_name=func_name,
                file_url=file_url,
                line_no=line_no,
                col_no=col_no,
                raw_frame=line_clean,
            )
        )

    return frames

