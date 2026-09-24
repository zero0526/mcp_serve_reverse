"""Blob & Large Media Storage Manager.

Tự động phát hiện và cách ly các thuộc tính dung lượng lớn (video, ảnh, audio, file nhị phân,
chuỗi Base64 Data URI, multipart chunks, hoặc payload quá cỡ) trong HTTP Request & Response,
lưu riêng ra thư mục `data/blobs/{session_id}/` và thay thế bằng tham chiếu gọn gàng ($blob_ref)
để bảo vệ Context Token của Agent và ngăn ngừa quá tải bộ nhớ/database.
"""

import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any
from app.infrastructure.config.settings import settings
# Đường dẫn mặc định thư mục lưu trữ blob
DEFAULT_BLOB_DIR = Path("/data/projects/web-apps/cli/mcp_server_reverse/data/blobs")

# Regex nhận diện Data URI Base64: data:image/png;base64,iVBORw...
DATA_URI_REGEX = re.compile(
    r"^data:(?P<mime>[a-zA-Z0-9_\-\.\/]+);base64,(?P<b64>[A-Za-z0-9+/=\s]+)$",
    re.DOTALL,
)

# Magic bytes nhận diện định dạng file media phổ biến
MAGIC_NUMBERS: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF", "application/pdf", ".pdf"),
    (b"PK\x03\x04", "application/zip", ".zip"),
    (b"\x1f\x8b", "application/gzip", ".gz"),
    (b"\x1a\x45\xdf\xa3", "video/webm", ".webm"),
    (b"ID3", "audio/mpeg", ".mp3"),
    (b"\xff\xfb", "audio/mpeg", ".mp3"),
    (b"\xff\xf3", "audio/mpeg", ".mp3"),
    (b"\xff\xf2", "audio/mpeg", ".mp3"),
    (b"OggS", "audio/ogg", ".ogg"),
    (b"RIFF", "audio/wav", ".wav"),  # Cần kiểm tra WAVE hoặc WEBP
]


def detect_mime_and_extension(data_bytes: bytes) -> tuple[str, str]:
    """Nhận diện MIME type và đuôi file dựa trên Magic Bytes."""
    if len(data_bytes) >= 12 and data_bytes[:4] == b"RIFF":
        if data_bytes[8:12] == b"WEBP":
            return "image/webp", ".webp"
        if data_bytes[8:12] == b"WAVE":
            return "audio/wav", ".wav"

    if len(data_bytes) >= 8 and data_bytes[4:8] == b"ftyp":
        # MP4 container
        return "video/mp4", ".mp4"

    for magic, mime, ext in MAGIC_NUMBERS:
        if data_bytes.startswith(magic):
            return mime, ext

    return "application/octet-stream", ".bin"


def is_probable_base64_media(s: str) -> tuple[bool, bytes | None, str, str]:
    """Kiểm tra xem chuỗi có phải là Base64 của file media (ảnh, video, audio, archive) không."""
    s_clean = s.strip()
    # Kiểm tra độ dài tối thiểu và các ký tự hợp lệ của base64
    if len(s_clean) < 512 or len(s_clean) % 4 != 0:
        return False, None, "", ""

    # Chuỗi Base64 thật luôn có độ đa dạng ký tự nhất định (entropy)
    if len(set(s_clean[:128])) < 10:
        return False, None, "", ""

    # Kiểm tra nhanh ký tự hợp lệ
    if not re.match(r"^[A-Za-z0-9+/]+={0,2}$", s_clean):
        return False, None, "", ""

    try:
        raw = base64.b64decode(s_clean, validate=True)
        if len(raw) < 256:
            return False, None, "", ""

        mime, ext = detect_mime_and_extension(raw)
        # Nếu nhận diện được định dạng media rõ ràng
        if mime != "application/octet-stream" or ext != ".bin":
            return True, raw, mime, ext

        # Nếu không có magic byte rõ ràng, kiểm tra tỷ lệ non-printable bytes
        # Nếu > 30% là non-ascii byte -> là dữ liệu nhị phân
        non_printable = sum(1 for b in raw[:512] if b < 32 and b not in (9, 10, 13))
        if non_printable > 50:
            return True, raw, "application/octet-stream", ".bin"

        return False, None, "", ""
    except Exception:
        return False, None, "", ""


class BlobStorageManager:
    """Quản lý lưu trữ và phân giải các Blob lớn ngoài database."""

    def __init__(self, base_dir: Path = DEFAULT_BLOB_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_session_dir(self, session_id: str) -> Path:
        s_dir = self.base_dir / session_id
        s_dir.mkdir(parents=True, exist_ok=True)
        return s_dir

    def save_blob(
        self,
        session_id: str,
        data_bytes: bytes,
        mime_type: str | None = None,
        ext: str | None = None,
        original_format: str = "binary",
    ) -> dict[str, Any]:
        """Lưu một mảng byte nhị phân ra đĩa và trả về dictionary tham chiếu $blob_ref."""
        if not mime_type or not ext:
            detected_mime, detected_ext = detect_mime_and_extension(data_bytes)
            mime_type = mime_type or detected_mime
            ext = ext or detected_ext

        sha256 = hashlib.sha256(data_bytes).hexdigest()
        blob_id = f"blob_{sha256[:16]}"
        filename = f"{blob_id}{ext}"
        session_dir = self.get_session_dir(session_id)
        file_path = session_dir / filename

        # Ghi file nếu chưa tồn tại (idempotent deduplication)
        if not file_path.exists():
            file_path.write_bytes(data_bytes)

        size_bytes = len(data_bytes)
        # Sinh chuỗi preview ngắn cho Agent dễ nhận biết loại dữ liệu
        if original_format == "data_uri":
            preview = f"data:{mime_type};base64,... [{size_bytes} bytes offloaded to disk]"
        elif original_format == "base64":
            preview = f"<Base64 {mime_type}: {size_bytes} bytes offloaded to disk>"
        else:
            preview = f"<{mime_type} binary: {size_bytes} bytes offloaded to disk>"

        rel_path = str(file_path.relative_to(self.base_dir.parent))

        return {
            "$blob_ref": blob_id,
            "file_path": str(file_path),
            "relative_path": rel_path,
            "mime_type": mime_type,
            "extension": ext,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "original_format": original_format,
            "is_offloaded": True,
            "preview": preview,
        }

    def offload_payload(
        self,
        data: Any,
        session_id: str,
        b64_threshold: int = 2048,
        oversized_threshold: int = settings.OVERSIZE_THRESHOLD,
        max_depth: int = 8,
    ) -> tuple[Any, int]:
        """Đệ quy quét và cách ly các thuộc tính dung lượng lớn ra thư mục data/blobs/.

        Trả về (cấu_trúc_đã_thay_thế, số_lượng_blob_đã_tách).
        """
        if max_depth <= 0 or data is None:
            return data, 0

        # 1. Xử lý kiểu bytes trực tiếp
        if isinstance(data, bytes):
            if len(data) >= 512:
                ref = self.save_blob(session_id, data, original_format="binary")
                return ref, 1
            return data, 0

        # 2. Xử lý kiểu str
        if isinstance(data, str):
            # 2.1. Kiểm tra Data URI Base64 (data:image/...;base64,...)
            if data.startswith("data:") and ";base64," in data[:100]:
                m = DATA_URI_REGEX.match(data)
                if m:
                    mime = m.group("mime")
                    b64_str = m.group("b64").strip()
                    try:
                        raw = base64.b64decode(b64_str)
                        if len(raw) >= 256:
                            _, ext = detect_mime_and_extension(raw)
                            ref = self.save_blob(
                                session_id,
                                raw,
                                mime_type=mime,
                                ext=ext,
                                original_format="data_uri",
                            )
                            return ref, 1
                    except Exception:
                        pass

            # 2.2. Kiểm tra Raw Base64 media lớn
            if len(data) >= b64_threshold:
                is_b64, raw, mime, ext = is_probable_base64_media(data)
                if is_b64 and raw:
                    ref = self.save_blob(
                        session_id,
                        raw,
                        mime_type=mime,
                        ext=ext,
                        original_format="base64",
                    )
                    return ref, 1

            # 2.3. Kiểm tra chuỗi quá lớn (Oversized string vượt ngưỡng)
            if len(data) >= oversized_threshold:
                raw = data.encode("utf-8")
                ref = self.save_blob(
                    session_id,
                    raw,
                    mime_type="text/plain",
                    ext=".txt",
                    original_format="oversized_text",
                )
                return ref, 1

            return data, 0

        # 3. Xử lý Dict
        if isinstance(data, dict):
            # Nếu đã là blob ref thì bỏ qua
            if "$blob_ref" in data and "file_path" in data:
                return data, 0

            new_dict = {}
            total_offloaded = 0
            for k, v in data.items():
                v_res, count = self.offload_payload(
                    v,
                    session_id=session_id,
                    b64_threshold=b64_threshold,
                    oversized_threshold=oversized_threshold,
                    max_depth=max_depth - 1,
                )
                new_dict[k] = v_res
                total_offloaded += count
            return new_dict, total_offloaded

        # 4. Xử lý List
        if isinstance(data, list):
            new_list = []
            total_offloaded = 0
            for item in data:
                item_res, count = self.offload_payload(
                    item,
                    session_id=session_id,
                    b64_threshold=b64_threshold,
                    oversized_threshold=oversized_threshold,
                    max_depth=max_depth - 1,
                )
                new_list.append(item_res)
                total_offloaded += count
            return new_list, total_offloaded

        return data, 0

    def read_blob_content(
        self,
        session_id: str,
        blob_id: str | None = None,
        file_path: str | None = None,
        format: str = "summary",
        offset: int = 0,
        max_bytes: int = 4096,
    ) -> dict[str, Any]:
        """Đọc và trích xuất nội dung của một Blob đã được cách ly ra đĩa.

        Hỗ trợ các format:
        - "summary": Chỉ trả về metadata (kích thước, MIME, sha256, path, hex preview).
        - "base64": Đọc nội dung (hoặc đoạn slice theo offset/max_bytes) mã hóa Base64.
        - "text": Đọc nội dung dưới dạng văn bản (UTF-8).
        - "path": Trả về đường dẫn file tuyệt đối để truyền trực tiếp vào script python.
        """
        target_path: Path | None = None
        if file_path:
            p = Path(file_path)
            if p.exists():
                target_path = p
        elif blob_id:
            session_dir = self.get_session_dir(session_id)
            matches = list(session_dir.glob(f"{blob_id}.*"))
            if matches:
                target_path = matches[0]

        if not target_path or not target_path.exists():
            return {
                "status": "NOT_FOUND",
                "message": f"Không tìm thấy blob file cho blob_id='{blob_id}' hoặc path='{file_path}'",
            }

        file_size = target_path.stat().st_size
        mime, ext = detect_mime_and_extension(target_path.read_bytes()[:64])

        if format == "path":
            return {
                "status": "COMPLETED",
                "blob_id": blob_id or target_path.stem,
                "file_path": str(target_path.resolve()),
                "size_bytes": file_size,
                "mime_type": mime,
            }

        # Đọc dữ liệu với phân đoạn slice
        with open(target_path, "rb") as f:
            if offset > 0:
                f.seek(offset)
            chunk = f.read(max_bytes)

        has_more = (offset + len(chunk)) < file_size

        if format == "base64":
            b64_content = base64.b64encode(chunk).decode("ascii")
            return {
                "status": "COMPLETED",
                "blob_id": blob_id or target_path.stem,
                "file_path": str(target_path.resolve()),
                "mime_type": mime,
                "size_bytes": file_size,
                "offset": offset,
                "chunk_bytes": len(chunk),
                "has_more": has_more,
                "data_base64": b64_content,
            }

        elif format == "text":
            text_preview = chunk.decode("utf-8", errors="replace")
            return {
                "status": "COMPLETED",
                "blob_id": blob_id or target_path.stem,
                "file_path": str(target_path.resolve()),
                "mime_type": mime,
                "size_bytes": file_size,
                "offset": offset,
                "chunk_bytes": len(chunk),
                "has_more": has_more,
                "text": text_preview,
            }

        # format == "summary" (mặc định)
        hex_preview = binascii.hexlify(chunk[:64]).decode("ascii")
        return {
            "status": "COMPLETED",
            "blob_id": blob_id or target_path.stem,
            "file_path": str(target_path.resolve()),
            "mime_type": mime,
            "extension": ext,
            "size_bytes": file_size,
            "has_more": has_more,
            "hex_preview_64b": hex_preview,
        }

    def hydrate_payload(self, data: Any) -> Any:
        """Khôi phục nội dung gốc từ các đối tượng tham chiếu $blob_ref."""
        if isinstance(data, dict):
            if "$blob_ref" in data and "file_path" in data:
                p = Path(data["file_path"])
                if p.exists():
                    raw_bytes = p.read_bytes()
                    orig_fmt = data.get("original_format", "binary")
                    if orig_fmt == "data_uri":
                        mime = data.get("mime_type", "application/octet-stream")
                        b64 = base64.b64encode(raw_bytes).decode("ascii")
                        return f"data:{mime};base64,{b64}"
                    elif orig_fmt == "base64":
                        return base64.b64encode(raw_bytes).decode("ascii")
                    elif orig_fmt == "oversized_text":
                        return raw_bytes.decode("utf-8", errors="replace")
                    return raw_bytes
            return {k: self.hydrate_payload(v) for k, v in data.items()}

        elif isinstance(data, list):
            return [self.hydrate_payload(item) for item in data]

        return data


# Singleton instance mặc định
default_blob_storage = BlobStorageManager()
