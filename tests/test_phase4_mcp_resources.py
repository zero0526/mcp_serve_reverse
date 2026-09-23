import json
import time
import uuid
import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.graph.entities import GraphEdge, GraphNode, NodeType, RelationType
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope
from app.interfaces.mcp.context import TruncationGuard, default_truncation_guard
from app.interfaces.mcp.server import create_mcp_server


def test_truncation_guard_string_and_list():
    """Kiểm tra hoạt động cắt ngắn chuỗi và mảng của TruncationGuard."""
    guard = TruncationGuard(max_string_len=50, max_list_items=5)

    # 1. Chuỗi ngắn -> giữ nguyên
    short_str, trunc1 = guard.truncate_string("hello world")
    assert short_str == "hello world"
    assert trunc1 is False

    # 2. Chuỗi dài -> cắt ngắn kèm thông báo
    long_str = "A" * 120
    guarded_str, trunc2 = guard.truncate_string(long_str)
    assert trunc2 is True
    assert guarded_str.startswith("A" * 50)
    assert "[TRUNCATED: omitted 70 characters" in guarded_str

    # 3. Mảng dài -> cắt ngắn còn max_list_items
    long_list = [f"item_{i}" for i in range(12)]
    res_list, trunc3, warnings = guard.guard_payload(long_list)
    assert trunc3 is True
    assert len(res_list) == 6  # 5 items + 1 truncated indicator string
    assert res_list[0] == "item_0"
    assert res_list[4] == "item_4"
    assert "[TRUNCATED: 7 more items omitted]" in res_list[5]
    assert any("List truncated" in w for w in warnings)


def test_truncation_guard_body_and_redaction():
    """Kiểm tra bảo vệ body và tích hợp che giấu dữ liệu nhạy cảm."""
    guard = TruncationGuard(max_body_len=100)

    # 1. Truncate body
    big_body = "x" * 250
    res_body, is_trunc, warn = guard.truncate_body(big_body)
    assert is_trunc is True
    assert "truncated" in warn.lower()
    assert len(res_body) < 250

    # 2. Quy trình trọn gói: Redaction + Truncation
    sensitive_data = {
        "user": "alice",
        "authorization": "Bearer secret_token_123456789",
        "cookie": "session_id=sess_secret_cookie_val",
        "nested": {
            "api_key": "api_key_extremely_secret_value",
            "items": ["a"] * 80,
        },
    }
    guarded, trunc_flag, warns = guard.process_resource_data(sensitive_data, redaction_mode="strict")
    # Kiểm tra redaction
    assert guarded["authorization"] == "[REDACTED]"
    assert guarded["cookie"] == "[REDACTED]"
    assert guarded["nested"]["api_key"] == "[REDACTED]"
    # Kiểm tra truncation mảng nested
    assert trunc_flag is True
    assert len(guarded["nested"]["items"]) <= 51


@pytest.mark.asyncio
async def test_mcp_session_resource_read():
    """Kiểm tra đọc resource session://{session_id} qua MCP Server."""
    server = create_mcp_server()
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)

    session_id = f"sess_res_{uuid.uuid4().hex[:8]}"
    await session_repo.create(
        session_id=session_id,
        name="MCP Resource Session Test",
        target="https://api.example.com",
        metadata={"environment": "test_sandbox"},
    )

    t_now = time.time_ns()
    req_id = f"req_{uuid.uuid4().hex[:8]}"

    # Ingest 1 request & response
    evt_req = EventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=t_now,
        payload={
            "request_id": req_id,
            "method": "GET",
            "url": "https://api.example.com/api/v1/profile",
            "headers": {"authorization": "Bearer secret_val_xyz"},
            "resource_type": "fetch",
        },
    )
    evt_res = EventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_RESPONSE,
        timestamp_ns=t_now + 5_000_000,
        payload={
            "request_id": req_id,
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body": {"user": "Alice", "role": "admin"},
        },
    )
    await ingest_uc.execute(evt_req)
    await ingest_uc.execute(evt_res)

    # 1. Đọc resource hợp lệ qua server.read_resource
    read_results = await server.read_resource(f"session://{session_id}")
    assert len(read_results) == 1
    content_obj = read_results[0]
    assert content_obj.mime_type == "application/json"

    data = json.loads(content_obj.content)
    assert data["uri"] == f"session://{session_id}"
    assert data["session"]["id"] == session_id
    assert data["session"]["name"] == "MCP Resource Session Test"
    assert data["session"]["metadata"]["environment"] == "test_sandbox"

    # Kiểm tra summary counts
    assert data["summary"]["counts"]["network_requests"] >= 1
    assert data["summary"]["counts"]["network_responses"] >= 1

    # Kiểm tra endpoints list
    assert len(data["summary"]["endpoints"]) >= 1
    ep = data["summary"]["endpoints"][0]
    assert ep["method"] == "GET"
    assert "/api/v1/profile" in ep["url"]

    # Kiểm tra metadata
    assert data["metadata"]["truncated"] is False

    # 2. Đọc session không tồn tại
    res_not_found = await server.read_resource("session://non_existent_session_id_999")
    assert len(res_not_found) == 1
    nf_data = json.loads(res_not_found[0].content)
    assert nf_data["error"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_mcp_request_resource_read():
    """Kiểm tra đọc resource request://{session_id}/{request_id} qua MCP Server."""
    server = create_mcp_server()
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)

    session_id = f"sess_req_res_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Request Resource Test", target="https://api.example.com")

    t_now = time.time_ns()
    req_id = f"req_action_{uuid.uuid4().hex[:8]}"

    # Ingest Request & Response
    evt_req = EventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=t_now,
        payload={
            "request_id": req_id,
            "method": "POST",
            "url": "https://api.example.com/api/v1/submit",
            "headers": {"authorization": "Bearer sensitive_token_abc"},
            "query": {"ref": "mcp_client"},
            "body": {"payload": "test_data"},
            "resource_type": "fetch",
        },
    )
    evt_res = EventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_RESPONSE,
        timestamp_ns=t_now + 10_000_000,
        payload={
            "request_id": req_id,
            "status_code": 201,
            "headers": {"set-cookie": "session=secret_cookie_val; Path=/"},
            "body": {"success": True, "record_id": 101},
        },
    )
    await ingest_uc.execute(evt_req)
    await ingest_uc.execute(evt_res)

    # 1. Đọc request resource
    read_results = await server.read_resource(f"request://{session_id}/{req_id}")
    assert len(read_results) == 1
    content_obj = read_results[0]
    assert content_obj.mime_type == "application/json"

    data = json.loads(content_obj.content)
    assert data["uri"] == f"request://{session_id}/{req_id}"
    assert data["request"]["method"] == "POST"
    assert "/api/v1/submit" in data["request"]["url"]
    assert data["request"]["headers"]["authorization"] == "[REDACTED]"
    assert data["response"]["status_code"] == 201
    assert data["response"]["headers"]["set-cookie"] == "[REDACTED]"

    # 2. Đọc request không tồn tại
    nf_results = await server.read_resource(f"request://{session_id}/non_existent_req_id")
    nf_data = json.loads(nf_results[0].content)
    assert nf_data["error"] == "REQUEST_NOT_FOUND"


@pytest.mark.asyncio
async def test_mcp_lineage_resource_read():
    """Kiểm tra đọc resource lineage://{session_id}/{node_id} qua MCP Server."""
    server = create_mcp_server()
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)

    session_id = f"sess_lin_res_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Lineage Resource Test", target="https://api.example.com")

    # Tạo Graph Nodes & Edges
    node_stor = GraphNode(
        id=f"node_stor_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        node_type=NodeType.STORAGE_ENTRY.value,
        entity_id="access_token",
        label="localStorage:access_token",
        properties={"storage_key": "access_token", "value": "jwt_val_123"},
    )
    node_req = GraphNode(
        id=f"node_req_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        node_type=NodeType.HTTP_REQUEST.value,
        entity_id="req_submit_001",
        label="POST /api/action",
        properties={"url": "https://api.example.com/api/action"},
    )
    edge = GraphEdge(
        session_id=session_id,
        source_id=node_stor.id,
        target_id=node_req.id,
        relation_type=RelationType.READS_FROM.value,
        confidence=0.98,
        properties={"storage_key": "access_token"},
    )

    await graph_repo.save_nodes([node_stor, node_req])
    await graph_repo.save_edges([edge])

    # 1. Đọc lineage resource cho node_req
    read_results = await server.read_resource(f"lineage://{session_id}/{node_req.id}")
    assert len(read_results) == 1
    content_obj = read_results[0]
    assert content_obj.mime_type == "application/json"

    data = json.loads(content_obj.content)
    assert data["uri"] == f"lineage://{session_id}/{node_req.id}"
    assert data["target_node"]["id"] == node_req.id
    assert data["target_node"]["label"] == "POST /api/action"

    # Kiểm tra upstream lineage
    upstream = data["upstream_lineage"]
    assert upstream is not None
    assert upstream["origin_node_id"] == node_stor.id
    assert upstream["overall_confidence"] >= 0.9
    assert len(upstream["steps"]) == 1
    assert upstream["steps"][0]["from_node_id"] == node_stor.id
    assert upstream["steps"][0]["to_node_id"] == node_req.id

    # 2. Đọc lineage resource cho node_stor (kiểm tra downstream usage)
    stor_results = await server.read_resource(f"lineage://{session_id}/{node_stor.id}")
    stor_data = json.loads(stor_results[0].content)
    assert len(stor_data["downstream_usage"]) >= 1
    assert stor_data["downstream_usage"][0]["target_node_id"] == node_req.id

    # 3. Đọc node không tồn tại
    nf_results = await server.read_resource(f"lineage://{session_id}/non_existent_node_999")
    nf_data = json.loads(nf_results[0].content)
    assert nf_data["error"] == "NODE_NOT_FOUND"
