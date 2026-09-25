"""
Bộ lưu trữ giá trị tách rời (ValueStore & ValueRef).
Chịu trách nhiệm bóc tách payload lớn ra khỏi đồ thị, băm SHA-256 và sinh ValueRef chuẩn hóa.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from dev.schema import ValueRef


class ValueStore:
    """
    Kho lưu trữ các giá trị thô (Raw Payloads) kèm tính toán băm SHA-256.
    Giúp đồ thị siêu nhẹ vì chỉ lưu ValueRef thay vì copy trực tiếp 5MB JSON/HTML vào node.
    """

    def __init__(self, storage_dir: Path | str | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("dev/blobs")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, Any] = {}

    def store(self, raw_value: Any, force_type: str | None = None) -> ValueRef:
        """
        Nạp một giá trị bất kỳ vào ValueStore và trả về đối tượng ValueRef gọn nhẹ.
        """
        if raw_value is None:
            raw_bytes = b""
            val_type = "null"
            preview = "null"
        elif isinstance(raw_value, bytes):
            raw_bytes = raw_value
            val_type = force_type or "blob"
            preview = f"[binary data: {len(raw_bytes)} bytes]"
        elif isinstance(raw_value, str):
            raw_bytes = raw_value.encode("utf-8")
            val_type = force_type or "string"
            preview = raw_value[:60].replace("\n", " ") + ("..." if len(raw_value) > 60 else "")
            # Thử nhận diện JSON string
            if raw_value.strip().startswith(("{", "[")):
                try:
                    json.loads(raw_value)
                    val_type = "json"
                except Exception:
                    pass
        elif isinstance(raw_value, (int, float)):
            raw_bytes = str(raw_value).encode("utf-8")
            val_type = "number"
            preview = str(raw_value)
        elif isinstance(raw_value, bool):
            raw_bytes = str(raw_value).lower().encode("utf-8")
            val_type = "boolean"
            preview = str(raw_value).lower()
        elif isinstance(raw_value, (dict, list)):
            dumped = json.dumps(raw_value, ensure_ascii=False)
            raw_bytes = dumped.encode("utf-8")
            val_type = force_type or "json"
            preview = dumped[:60].replace("\n", " ") + ("..." if len(dumped) > 60 else "")
        else:
            raw_bytes = str(raw_value).encode("utf-8")
            val_type = force_type or "string"
            preview = str(raw_value)[:60]

        # 1. Tính toán mã băm SHA-256
        digest = hashlib.sha256(raw_bytes).hexdigest()
        hash_str = f"sha256:{digest}"
        ref_id = f"val_{digest[:12]}"

        # 2. Lưu vào Memory Cache
        self._memory_cache[ref_id] = raw_value

        # 3. Nếu kích thước > 4KB, ghi file blob ra đĩa để giải phóng RAM
        if len(raw_bytes) > 4096:
            blob_file = self.storage_dir / f"{digest}.bin"
            if not blob_file.exists():
                blob_file.write_bytes(raw_bytes)

        return ValueRef(
            type=val_type,
            hash=hash_str,
            size=len(raw_bytes),
            ref=ref_id,
            preview=preview,
        )

    def load(self, ref_id: str) -> Any:
        """Truy xuất lại giá trị thô từ mã ref_id."""
        if ref_id in self._memory_cache:
            return self._memory_cache[ref_id]

        # Tìm trên đĩa nếu chưa có trong RAM
        digest_prefix = ref_id.replace("val_", "")
        for p in self.storage_dir.glob(f"{digest_prefix}*.bin"):
            return p.read_bytes()

        return None
