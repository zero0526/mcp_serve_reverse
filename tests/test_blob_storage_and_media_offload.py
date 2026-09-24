import base64
import json
import uuid
from pathlib import Path
import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel, SessionModel
from app.application.network.summarize_request import SummarizeRequestUseCase
from app.infrastructure.storage.blob_storage import (
    BlobStorageManager,
    default_blob_storage,
    detect_mime_and_extension,
)
from app.interfaces.mcp.tools.network import get_blob_content_tool


def test_detect_mime_and_extension():
    # JPEG magic bytes
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    mime, ext = detect_mime_and_extension(jpeg_bytes)
    assert mime == "image/jpeg"
    assert ext == ".jpg"

    # PNG magic bytes
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    mime, ext = detect_mime_and_extension(png_bytes)
    assert mime == "image/png"
    assert ext == ".png"

    # MP4 magic bytes
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
    mime, ext = detect_mime_and_extension(mp4_bytes)
    assert mime == "video/mp4"
    assert ext == ".mp4"

    # PDF magic bytes
    pdf_bytes = b"%PDF-1.5" + b"\x00" * 20
    mime, ext = detect_mime_and_extension(pdf_bytes)
    assert mime == "application/pdf"
    assert ext == ".pdf"


def test_offload_data_uri_and_raw_base64(tmp_path):
    storage = BlobStorageManager(base_dir=tmp_path / "blobs")
    session_id = f"sess_test_{uuid.uuid4().hex[:8]}"

    # Tạo một ảnh PNG giả lập kích thước 1KB
    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 250
    b64_png = base64.b64encode(png_data).decode("ascii")
    data_uri = f"data:image/png;base64,{b64_png}"

    payload = {
        "user_id": 12345,
        "avatar_upload": data_uri,
        "nested": {
            "title": "Profile Update",
            "thumbnail_b64": b64_png,
        },
    }

    offloaded, count = storage.offload_payload(payload, session_id=session_id, b64_threshold=1000)
    assert count == 2
    assert offloaded["user_id"] == 12345
    assert offloaded["nested"]["title"] == "Profile Update"

    # Xác nhận trường avatar_upload đã trở thành tham chiếu blob
    avatar_ref = offloaded["avatar_upload"]
    assert "$blob_ref" in avatar_ref
    assert avatar_ref["mime_type"] == "image/png"
    assert avatar_ref["extension"] == ".png"
    assert avatar_ref["is_offloaded"] is True
    assert Path(avatar_ref["file_path"]).exists()
    assert Path(avatar_ref["file_path"]).read_bytes() == png_data

    # Xác nhận thumbnail_b64 cũng được offload
    thumb_ref = offloaded["nested"]["thumbnail_b64"]
    assert "$blob_ref" in thumb_ref
    assert Path(thumb_ref["file_path"]).exists()

    # Kiểm tra khôi phục (hydrate)
    hydrated = storage.hydrate_payload(offloaded)
    assert hydrated["avatar_upload"] == data_uri
    assert hydrated["nested"]["thumbnail_b64"] == b64_png


def test_offload_oversized_text(tmp_path):
    storage = BlobStorageManager(base_dir=tmp_path / "blobs")
    session_id = f"sess_oversize_{uuid.uuid4().hex[:8]}"

    huge_text = "A" * 20000  # 20KB text
    payload = {"short": "ok", "huge": huge_text}

    offloaded, count = storage.offload_payload(payload, session_id=session_id, oversized_threshold=15000)
    assert count == 1
    assert offloaded["short"] == "ok"
    huge_ref = offloaded["huge"]
    assert "$blob_ref" in huge_ref
    assert huge_ref["mime_type"] == "text/plain"
    assert huge_ref["size_bytes"] == 20000
    assert Path(huge_ref["file_path"]).exists()


@pytest.mark.asyncio
async def test_get_blob_content_tool(tmp_path):
    session_id = f"sess_tool_{uuid.uuid4().hex[:8]}"
    storage = BlobStorageManager(base_dir=tmp_path / "blobs")

    sample_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"TESTIMAGEPAYLOAD" * 50
    ref = storage.save_blob(session_id, sample_bytes, mime_type="image/jpeg", ext=".jpg")
    file_path = ref["file_path"]
    blob_id = ref["$blob_ref"]

    # Thay tạm default_blob_storage để test tool
    from unittest.mock import patch
    with patch("app.interfaces.mcp.tools.network.default_blob_storage", storage):
        # 1. Format summary
        res_sum = await get_blob_content_tool(session_id=session_id, blob_id=blob_id, format="summary")
        assert res_sum["status"] == "COMPLETED"
        assert res_sum["data"]["mime_type"] == "image/jpeg"
        assert res_sum["data"]["size_bytes"] == len(sample_bytes)
        assert "hex_preview_64b" in res_sum["data"]

        # 2. Format path (để dùng trong python script)
        res_path = await get_blob_content_tool(session_id=session_id, blob_id=blob_id, format="path")
        assert res_path["status"] == "COMPLETED"
        assert res_path["data"]["file_path"] == file_path

        # 3. Format base64 với chunk/slice
        res_b64 = await get_blob_content_tool(
            session_id=session_id, blob_id=blob_id, format="base64", offset=0, max_bytes=64
        )
        assert res_b64["status"] == "COMPLETED"
        decoded = base64.b64decode(res_b64["data"]["data_base64"])
        assert decoded == sample_bytes[:64]
        assert res_b64["data"]["has_more"] is True


@pytest.mark.asyncio
async def test_summarize_request_with_blob_offload():
    session_id = f"sess_media_{uuid.uuid4().hex[:8]}"
    req_id = f"req_{uuid.uuid4().hex[:8]}"

    # Giả lập upload video qua GraphQL variables
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00\x01\x02" * 400
    b64_video = base64.b64encode(mp4_bytes).decode("ascii")
    data_uri_video = f"data:video/mp4;base64,{b64_video}"

    req_body_obj = {
        "operationName": "UploadReelVideoMutation",
        "variables": {
            "title": "My Viral Reel",
            "video_file": data_uri_video,
        },
    }

    async with AsyncSessionLocal() as db:
        sess = SessionModel(
            id=session_id,
            source="browser",
            name="Media Upload Session",
            status="active",
            target="https://facebook.com",
            started_at_ns=1000,
            created_at_ns=1000,
            updated_at_ns=1000,
        )
        db.add(sess)

        req = NetworkRequestModel(
            id=req_id,
            session_id=session_id,
            url="https://www.facebook.com/api/graphql/",
            method="POST",
            host="www.facebook.com",
            path="/api/graphql/",
            resource_type="xhr",
            started_at_ns=1000,
            headers_json=json.dumps({"Content-Type": "application/json"}),
            body_json=json.dumps(req_body_obj),
        )
        db.add(req)
        await db.commit()

    uc = SummarizeRequestUseCase(session_factory=AsyncSessionLocal)
    summary = await uc.execute(session_id=session_id, request_id=req_id)
    assert summary is not None

    body = summary["body"]
    assert body["operationName"] == "UploadReelVideoMutation"
    assert body["variables"]["title"] == "My Viral Reel"

    video_ref = body["variables"]["video_file"]
    # Kiểm tra thuộc tính video lớn đã được cách ly ra thư mục data/blobs
    assert isinstance(video_ref, dict)
    assert "$blob_ref" in video_ref
    assert video_ref["mime_type"] == "video/mp4"
    assert video_ref["extension"] == ".mp4"
    assert video_ref["is_offloaded"] is True
    assert Path(video_ref["file_path"]).exists()
    assert Path(video_ref["file_path"]).read_bytes() == mp4_bytes
