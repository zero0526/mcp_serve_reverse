import json
import time
import uuid
import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.models import NetworkRequestModel, NetworkResponseModel
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.graph.project_session_graph import ProjectSessionGraphUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.graph.nodes import GraphNode, NodeType
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope
from app.interfaces.mcp.server import create_mcp_server
from app.interfaces.mcp.tools.capture import list_sessions_tool
from app.interfaces.mcp.tools.graph import compact_graph_tool, rebuild_graph_tool
from app.interfaces.mcp.tools.lineage import differential_analysis_tool
from app.interfaces.mcp.tools.network import list_requests_tool


def test_mcp_server_registers_all_new_tools():
    """Kiểm tra server MCP đã đăng ký đầy đủ 5 tools mới."""
    server = create_mcp_server()
    registered_tools = server._tool_manager._tools

    assert "differential_analysis" in registered_tools
    assert "rebuild_graph" in registered_tools
    assert "compact_graph" in registered_tools
    assert "list_sessions" in registered_tools
    assert "list_requests" in registered_tools
    assert "detect_security_challenges" in registered_tools


@pytest.mark.asyncio
async def test_list_sessions_tool():
    """Kiểm tra list_sessions_tool hỗ trợ phân trang và lọc theo task_id."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    task_id = f"task_test_{uuid.uuid4().hex[:8]}"
    s1_id = f"sess_ls_1_{uuid.uuid4().hex[:8]}"
    s2_id = f"sess_ls_2_{uuid.uuid4().hex[:8]}"

    # Tạo 2 session giả lập
    await session_repo.create(
        session_id=s1_id,
        name="Session 1",
        target="https://example.com/login",
        source="browser",
        task_id=task_id,
        metadata={"task_id": task_id},
    )
    await session_repo.create(
        session_id=s2_id,
        name="Session 2",
        target="https://example.com/checkout",
        source="browser",
        task_id=task_id,
        metadata={"task_id": task_id},
    )

    # 1. Lọc theo task_id
    res_task = await list_sessions_tool(task_id=task_id)
    assert res_task["status"] == "COMPLETED"
    assert len(res_task["data"]["sessions"]) >= 2
    session_ids = [s["id"] for s in res_task["data"]["sessions"]]
    assert s1_id in session_ids
    assert s2_id in session_ids

    # 2. Liệt kê toàn cục với pagination
    res_all = await list_sessions_tool(limit=10, offset=0)
    assert res_all["status"] == "COMPLETED"
    assert "sessions" in res_all["data"]
    assert len(res_all["data"]["sessions"]) <= 10


@pytest.mark.asyncio
async def test_list_requests_tool():
    """Kiểm tra list_requests_tool lọc theo method và url_keyword."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    session_id = f"sess_req_{uuid.uuid4().hex[:8]}"
    now_ns = time.time_ns()

    await session_repo.create(
        session_id=session_id,
        name="Test Req Session",
        target="https://example.com",
        source="browser",
    )

    async with AsyncSessionLocal() as db:
        # Thêm 2 requests: 1 GET và 1 POST
        r1 = NetworkRequestModel(
            id=f"req_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            page_id="page_1",
            method="GET",
            url="https://example.com/api/v1/user/profile",
            path="/api/v1/user/profile",
            headers_json=json.dumps({"Authorization": "Bearer secret_token"}),
            query_json=json.dumps({"lang": "vi"}),
            body_json="{}",
            started_at_ns=now_ns + 10,
        )
        r2 = NetworkRequestModel(
            id=f"req_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            page_id="page_1",
            method="POST",
            url="https://example.com/api/v1/order/checkout",
            path="/api/v1/order/checkout",
            headers_json=json.dumps({"Content-Type": "application/json"}),
            query_json="{}",
            body_json=json.dumps({"item_id": 999, "qty": 2}),
            started_at_ns=now_ns + 20,
        )
        db.add_all([r1, r2])

        resp2 = NetworkResponseModel(
            id=f"resp_{uuid.uuid4().hex[:8]}",
            request_id=r2.id,
            status_code=201,
            headers_json="{}",
            body_json=json.dumps({"order_id": "ORD-12345"}),
            received_at_ns=now_ns + 30,
        )
        db.add(resp2)
        await db.commit()

    # 1. Liệt kê tất cả
    all_res = await list_requests_tool(session_id=session_id)
    assert all_res["status"] == "COMPLETED"
    assert len(all_res["data"]["requests"]) == 2

    # 2. Lọc method POST
    post_res = await list_requests_tool(session_id=session_id, method="POST")
    assert post_res["status"] == "COMPLETED"
    assert len(post_res["data"]["requests"]) == 1
    req_item = post_res["data"]["requests"][0]
    assert req_item["method"] == "POST"
    assert req_item["status_code"] == 201
    assert req_item["has_payload"] is True

    # 3. Lọc keyword
    search_res = await list_requests_tool(session_id=session_id, url_keyword="profile")
    assert search_res["status"] == "COMPLETED"
    assert len(search_res["data"]["requests"]) == 1
    assert search_res["data"]["requests"][0]["method"] == "GET"


@pytest.mark.asyncio
async def test_rebuild_and_compact_graph_tools():
    """Kiểm tra rebuild_graph_tool và compact_graph_tool trên session."""
    session_id = f"sess_graph_{uuid.uuid4().hex[:8]}"
    now_ns = time.time_ns()

    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    await session_repo.create(
        session_id=session_id,
        name="Graph Test Session",
        target="https://example.com",
        source="browser",
    )

    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)
    project_uc = ProjectSessionGraphUseCase(graph_repository=graph_repo, session_factory=AsyncSessionLocal)

    # 1. Ingest một số sự kiện
    evt1 = EventEnvelope(
        event_id=f"evt1_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.STORAGE_WRITE,
        timestamp_ns=now_ns,
        payload={"storage_type": "local_storage", "storage_key": "auth_token", "value_preview": "tok_123"},
    )
    evt2 = EventEnvelope(
        event_id=f"evt2_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=now_ns + 10,
        payload={
            "request_id": f"req_{uuid.uuid4().hex[:8]}",
            "method": "GET",
            "url": "https://example.com/assets/logo.png",
            "headers": {"authorization": "Bearer tok_123"},
        },
    )
    await ingest_uc.execute(evt1)
    await ingest_uc.execute(evt2)

    # Project đồ thị ban đầu
    await project_uc.execute(session_id=session_id)

    # Thêm một node cô lập (isolated node)
    isolated_node = GraphNode(
        id=f"node_iso_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        node_type=NodeType.VALUE,
        label="Isolated Trash Node",
        created_at_ns=now_ns,
    )
    await graph_repo.save_nodes([isolated_node])

    # 2. Kiểm thử rebuild_graph_tool
    rebuild_res = await rebuild_graph_tool(session_id=session_id)
    assert rebuild_res["status"] == "COMPLETED"
    assert "nodes_count" in rebuild_res["data"]
    assert rebuild_res["data"]["nodes_count"] >= 2

    # 3. Kiểm thử compact_graph_tool: tỉa file tĩnh (.png) và isolated
    compact_res = await compact_graph_tool(
        session_id=session_id,
        prune_static=True,
        prune_internals=True,
        prune_isolated=True,
    )
    assert compact_res["status"] == "COMPLETED"
    assert "pruned_nodes_count" in compact_res["data"]
    assert "remaining_nodes_count" in compact_res["data"]


@pytest.mark.asyncio
async def test_differential_analysis_tool():
    """Kiểm tra differential_analysis_tool so sánh các session cùng task_id."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    task_id = f"task_diff_{uuid.uuid4().hex[:8]}"
    now_ns = time.time_ns()

    s1_id = f"sess_diff_1_{uuid.uuid4().hex[:8]}"
    s2_id = f"sess_diff_2_{uuid.uuid4().hex[:8]}"

    await session_repo.create(
        session_id=s1_id,
        name="Session A",
        target="https://example.com",
        source="browser",
        task_id=task_id,
        metadata={"task_id": task_id},
    )
    await session_repo.create(
        session_id=s2_id,
        name="Session B",
        target="https://example.com",
        source="browser",
        task_id=task_id,
        metadata={"task_id": task_id},
    )

    async with AsyncSessionLocal() as db:
        # Cùng một endpoint nhưng Session 1 có timestamp & name khác Session 2
        r1 = NetworkRequestModel(
            id=f"req_{uuid.uuid4().hex[:8]}",
            session_id=s1_id,
            page_id="page_1",
            method="POST",
            url="https://example.com/api/register",
            path="/api/register",
            headers_json=json.dumps({"X-Timestamp": "1700000000"}),
            query_json=json.dumps({"app_id": "constant_app_123"}),
            body_json=json.dumps({"username": "alice", "action": "create"}),
            started_at_ns=now_ns + 10,
        )
        r2 = NetworkRequestModel(
            id=f"req_{uuid.uuid4().hex[:8]}",
            session_id=s2_id,
            page_id="page_1",
            method="POST",
            url="https://example.com/api/register",
            path="/api/register",
            headers_json=json.dumps({"X-Timestamp": "1700000050"}),
            query_json=json.dumps({"app_id": "constant_app_123"}),
            body_json=json.dumps({"username": "bob", "action": "create"}),
            started_at_ns=now_ns + 2010,
        )
        db.add_all([r1, r2])
        await db.commit()

    diff_res = await differential_analysis_tool(task_id=task_id)
    assert diff_res["status"] == "COMPLETED"
    assert diff_res["data"]["task_id"] == task_id
    assert set(diff_res["data"]["session_ids"]) == {s1_id, s2_id}

    # Kiểm tra phân loại tham số
    data = diff_res["data"]
    assert "summary" in data
    assert "variances" in data
    assert len(data["classified_constants"]) >= 1 or len(data["variances"]) >= 1
