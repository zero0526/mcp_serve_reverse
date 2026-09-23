import time
import uuid
import pytest
from sqlalchemy import select

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.models import (
    FunctionExecutionModel,
    NetworkRequestModel,
    TraceEventModel,
)
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.ingest.ingest_event import IngestEventUseCase
from app.application.lineage.find_transformations import FindTransformationsUseCase
from app.application.trace.get_execution_context import GetExecutionContextUseCase
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope
from app.infrastructure.serialization.json import safe_dumps
from app.interfaces.mcp.tools.lineage import find_transformations_tool
from app.interfaces.mcp.tools.trace import get_execution_context_tool


@pytest.mark.asyncio
async def test_find_transformations_full_pipeline():
    """Kiểm thử phát hiện và phân tích chuỗi biến đổi dữ liệu (FindTransformationsUseCase).

    Chuỗi kiểm thử: raw_dict -> JSON.stringify -> crypto.subtle.digest (SHA-256) -> btoa -> HTTP Header (x-signature).
    """
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)
    find_trans_uc = FindTransformationsUseCase(graph_repository=graph_repo)

    session_id = f"sess_trans_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Transform Pipeline Test", target="https://example.com")

    t_base = time.time_ns()

    # 1. Step 1: Serialize JSON (JSON.stringify)
    evt_serialize = EventEnvelope(
        event_id=f"evt_ser_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.SERIALIZE,
        timestamp_ns=t_base + 10_000_000,
        execution_id="exec_serialize_01",
        payload={
            "target_type": "json",
            "input": {"username": "admin", "nonce": "nonce_12345"},
            "output": '{"username":"admin","nonce":"nonce_12345"}',
        },
    )

    # 2. Step 2: Crypto Digest (crypto.subtle.digest SHA-256)
    evt_crypto = EventEnvelope(
        event_id=f"evt_cry_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.CRYPTO_OPERATION,
        timestamp_ns=t_base + 20_000_000,
        execution_id="exec_crypto_02",
        payload={
            "operation": "digest",
            "algorithm": "SHA-256",
            "input_preview": '{"username":"admin","nonce":"nonce_12345"}',
            "output_preview": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
    )

    # 3. Step 3: Base64 Encode (btoa)
    evt_encode = EventEnvelope(
        event_id=f"evt_enc_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.FUNCTION_CALL,
        timestamp_ns=t_base + 30_000_000,
        execution_id="exec_btoa_03",
        payload={
            "function_name": "btoa",
            "arguments": ["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
            "return_value": "NDdlZTBjNDQyOThmYzFjMTQ5YWZiZjRjODk5NmZiOTI0MjdhZTQxZTQ2NDliOTM0Y2E0OTU5OTFiNzg1MmI4NTU=",
        },
    )

    # 4. Destination Sink: Network Request có header x-signature mang giá trị từ btoa
    req_id = f"req_sig_{uuid.uuid4().hex[:8]}"
    evt_req = EventEnvelope(
        event_id=f"evt_req_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=t_base + 40_000_000,
        execution_id="exec_caller_req",
        payload={
            "request_id": req_id,
            "method": "POST",
            "url": "https://api.example.com/auth/signed-action",
            "headers": {
                "content-type": "application/json",
                "x-signature": "NDdlZTBjNDQyOThmYzFjMTQ5YWZiZjRjODk5NmZiOTI0MjdhZTQxZTQ2NDliOTM0Y2E0OTU5OTFiNzg1MmI4NTU=",
            },
            "body": '{"username":"admin"}',
        },
    )

    await ingest_uc.execute(evt_serialize)
    await ingest_uc.execute(evt_crypto)
    await ingest_uc.execute(evt_encode)
    await ingest_uc.execute(evt_req)

    # ═══════════════════════════════════════════════════════════════════════
    # Test A: Phân tích toàn bộ pipeline (forward + backward)
    # ═══════════════════════════════════════════════════════════════════════
    res = await find_trans_uc.execute(session_id=session_id)
    assert res["count"] >= 3
    assert len(res["transformations"]) >= 3

    steps = res["transformations"]
    assert any(s["function_name"] == "JSON.stringify" for s in steps)
    assert any("crypto.subtle" in s["function_name"] for s in steps)
    assert any(s["function_name"] == "btoa" for s in steps)

    summary = res["chain_summary"]
    assert "JSON.stringify" in summary
    assert "crypto.subtle" in summary
    assert "btoa" in summary
    assert "headers.x-signature" in summary or "Destination" in summary

    # ═══════════════════════════════════════════════════════════════════════
    # Test B: Lọc theo transformation_types = ["hash"]
    # ═══════════════════════════════════════════════════════════════════════
    res_hash_only = await find_trans_uc.execute(
        session_id=session_id,
        transformation_types=["hash"],
    )
    assert res_hash_only["count"] == 1
    assert "crypto.subtle" in res_hash_only["transformations"][0]["function_name"]

    # ═══════════════════════════════════════════════════════════════════════
    # Test C: Lọc theo target x-signature và direction = backward
    # ═══════════════════════════════════════════════════════════════════════
    res_backward = await find_trans_uc.execute(
        session_id=session_id,
        target="x-signature",
        direction="backward",
    )
    assert res_backward["direction"] == "backward"
    assert res_backward["count"] >= 3
    # Khi direction = backward, bước cuối cùng trong forward trở thành phần tử đầu tiên
    assert res_backward["transformations"][0]["function_name"] == "btoa"


@pytest.mark.asyncio
async def test_get_execution_context_caller_callee_and_network():
    """Kiểm thử truy xuất ngữ cảnh thực thi hàm (GetExecutionContextUseCase).

    Bao gồm caller, callee, arguments có redaction, return value, call stack V8 và request liên quan.
    """
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    context_uc = GetExecutionContextUseCase(session_factory=AsyncSessionLocal, graph_repo=graph_repo)

    session_id = f"sess_ctx_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Context Test", target="https://example.com")

    t_now = time.time_ns()
    exec_caller = f"exec_caller_{uuid.uuid4().hex[:6]}"
    exec_target = f"exec_target_{uuid.uuid4().hex[:6]}"
    exec_callee = f"exec_callee_{uuid.uuid4().hex[:6]}"

    # Ghi nhận dữ liệu vào cơ sở dữ liệu SQLite
    async with AsyncSessionLocal() as db:
        # 1. Caller Execution
        caller_row = FunctionExecutionModel(
            id=exec_caller,
            session_id=session_id,
            function_name="onFormSubmit",
            module_name="app.bundle.js",
            source_location="app.bundle.js:120:5",
            started_at_ns=t_now,
            ended_at_ns=t_now + 50_000_000,
            status="completed",
        )
        # 2. Target Execution (với sensitive args & return value)
        target_row = FunctionExecutionModel(
            id=exec_target,
            session_id=session_id,
            function_name="buildAuthSignature",
            module_name="auth.js",
            source_location="auth.js:42:15",
            parent_execution_id=exec_caller,
            started_at_ns=t_now + 10_000_000,
            ended_at_ns=t_now + 30_000_000,
            status="completed",
            arguments_json=safe_dumps([
                {"username": "johndoe", "password": "super_secret_password_123"},
                "Bearer secret_token_xyz_456",
            ]),
            return_value_ref="Bearer secret_token_xyz_456_signed",
            stack_trace="""Error
    at buildAuthSignature (https://example.com/assets/auth.js:42:15)
    at onFormSubmit (https://example.com/assets/app.bundle.js:120:5)
    at HTMLButtonElement.dispatch (https://example.com/assets/vendor.js:500:10)""",
        )
        # 3. Callee Execution
        callee_row = FunctionExecutionModel(
            id=exec_callee,
            session_id=session_id,
            function_name="computeHmacSha256",
            module_name="crypto_util.js",
            source_location="crypto_util.js:18:2",
            parent_execution_id=exec_target,
            started_at_ns=t_now + 15_000_000,
            ended_at_ns=t_now + 25_000_000,
            status="completed",
        )
        # 4. Network Request được kích hoạt trực tiếp từ exec_target
        req_id = f"req_ctx_{uuid.uuid4().hex[:6]}"
        req_row = NetworkRequestModel(
            id=req_id,
            session_id=session_id,
            execution_id=exec_target,
            method="POST",
            url="https://api.example.com/auth/login",
            started_at_ns=t_now + 28_000_000,
            status="captured",
        )

        db.add_all([caller_row, target_row, callee_row, req_row])
        await db.commit()

    # Thực thi use case
    ctx = await context_uc.execute(session_id=session_id, execution_id=exec_target)

    assert ctx["found"] is True
    assert ctx["execution"]["execution_id"] == exec_target
    assert ctx["execution"]["function_name"] == "buildAuthSignature"
    assert ctx["execution"]["parent_execution_id"] == exec_caller

    # Kiểm tra Caller / Callee Tree
    tree = ctx["call_tree"]
    assert tree["caller"] is not None
    assert tree["caller"]["execution_id"] == exec_caller
    assert tree["caller"]["function_name"] == "onFormSubmit"

    assert tree["callees_count"] >= 1
    assert any(c["execution_id"] == exec_callee and c["function_name"] == "computeHmacSha256" for c in tree["callees"])

    # Kiểm tra Redaction trên Arguments & Return Value
    args = ctx["arguments"]
    assert len(args) == 2
    # Argument 0: dict có password -> phải được che giấu
    assert args[0]["redacted"] is True
    assert "super_secret_password_123" not in str(args[0]["value"])
    assert "[REDACTED:" in str(args[0]["value"])

    # Argument 1: string token -> phải được che giấu
    assert args[1]["redacted"] is True
    assert "secret_token_xyz_456" not in str(args[1]["value"])

    # Return value: string token -> phải được che giấu
    ret = ctx["return_value"]
    assert ret is not None
    assert ret["redacted"] is True
    assert "secret_token_xyz_456_signed" not in str(ret["value"])

    # Kiểm tra Phân tách Call Stack V8
    stack_frames = ctx["stack_trace"]
    assert len(stack_frames) >= 2
    assert stack_frames[0]["function_name"] == "buildAuthSignature"
    assert stack_frames[0]["line_no"] == 42
    assert stack_frames[1]["function_name"] == "onFormSubmit"
    assert stack_frames[1]["line_no"] == 120

    # Kiểm tra Related Network Requests
    related_reqs = ctx["related_requests"]
    assert len(related_reqs) >= 1
    assert any(r["request_id"] == req_id and r["directly_triggered"] is True for r in related_reqs)


@pytest.mark.asyncio
async def test_mcp_tools_layer_for_transformations_and_context():
    """Kiểm thử tầng MCP Tool wrapper cho find_transformations và get_execution_context."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    session_id = f"sess_mcp_tool_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="MCP Tool Test", target="https://example.com")

    # 1. Gọi find_transformations_tool qua MCP wrapper
    mcp_trans = await find_transformations_tool(session_id=session_id)
    assert mcp_trans["status"] == "COMPLETED"
    assert "data" in mcp_trans
    assert mcp_trans["data"]["session_id"] == session_id

    # 2. Gọi get_execution_context_tool qua MCP wrapper
    mcp_ctx = await get_execution_context_tool(session_id=session_id, execution_id="non_existent_exec")
    assert mcp_ctx["status"] == "NOT_FOUND"
    assert mcp_ctx["data"]["found"] is False
