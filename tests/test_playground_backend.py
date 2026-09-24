"""Kiểm thử liên thông toàn bộ Playground Backend REST APIs."""

import pytest
from starlette.testclient import TestClient

from app.adapters.persistence.sqlite.connection import init_db
from playground.backend.main import app


@pytest.fixture(scope="module", autouse=True)
def init_test_database():
    """Khởi tạo cấu trúc bảng SQLite trước khi chạy test."""
    import asyncio
    asyncio.run(init_db())


@pytest.fixture
def client():
    """Tạo TestClient cho ứng dụng Starlette."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client: TestClient):
    """Kiểm tra endpoint /api/health."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "mcp-reverse-studio-api"


def test_task_lifecycle_api(client: TestClient):
    """Kiểm tra chu trình Task: Tạo task, liệt kê, chi tiết, cập nhật status."""
    # 1. Tạo Task với 2 initial URLs
    create_payload = {
        "name": "Shopee Cart API Reversal",
        "goal_description": "Capture cart signature generation",
        "instructions": "Navigate and add to cart",
        "env_vars": {"PROXY": "VN_LOCAL"},
        "initial_urls": [
            "https://shopee.vn/api/v4/item/get?itemid=111",
            "https://shopee.vn/api/v4/cart/add_to_cart",
        ],
        "browser_config": {
            "headless": True,
            "use_cloakbrowser": True,
        },
    }
    res = client.post("/api/tasks", json=create_payload)
    assert res.status_code == 201
    task_data = res.json()
    task_id = task_data["id"]
    assert task_data["name"] == "Shopee Cart API Reversal"
    assert len(task_data["session_ids"]) == 2
    assert task_data["status"] == "CREATED"

    # 2. Liệt kê tasks
    res_list = client.get("/api/tasks")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["count"] >= 1
    found = any(t["id"] == task_id for t in list_data["tasks"])
    assert found

    # 3. Chi tiết task
    res_detail = client.get(f"/api/tasks/{task_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == task_id

    # 4. Cập nhật status task
    res_patch = client.patch(f"/api/tasks/{task_id}/status", json={"status": "IN_PROGRESS"})
    assert res_patch.status_code == 200
    assert res_patch.json()["success"] is True

    # Xác nhận status đã đổi
    res_verify = client.get(f"/api/tasks/{task_id}")
    assert res_verify.json()["status"] == "IN_PROGRESS"


def test_session_lifecycle_api(client: TestClient):
    """Kiểm tra chu trình Session: Lấy danh sách theo task, launch, close, status."""
    # Tạo task trước
    res_t = client.post(
        "/api/tasks",
        json={
            "name": "Session Test Task",
            "goal_description": "Test session actions",
            "initial_urls": ["https://example.com/checkout"],
        },
    )
    task_id = res_t.json()["id"]
    session_id = res_t.json()["session_ids"][0]

    # 1. Liệt kê sessions theo task_id
    res_s = client.get(f"/api/sessions?task_id={task_id}")
    assert res_s.status_code == 200
    sessions = res_s.json()
    assert len(sessions) >= 1
    target_session = next(s for s in sessions if s["id"] == session_id)
    assert target_session["status"] == "CREATED"

    # 2. Launch session
    res_launch = client.post(f"/api/sessions/{session_id}/launch")
    assert res_launch.status_code == 200
    assert res_launch.json()["success"] is True

    # 3. Kiểm tra status session
    res_status = client.get(f"/api/sessions/{session_id}/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "RUNNING"

    # 4. Close session & Project graph
    res_close = client.post(f"/api/sessions/{session_id}/close")
    assert res_close.status_code == 200
    assert res_close.json()["success"] is True
    assert res_close.json()["status"] == "STOPPED"


def test_graph_api(client: TestClient):
    """Kiểm tra Graph Studio APIs: Xem graph, update alias, delete node."""
    import asyncio
    import uuid
    from app.domain.graph.nodes import GraphNode, NodeType
    from app.domain.graph.edges import GraphEdge
    from app.domain.graph.relations import RelationType
    from playground.backend.dependencies import get_container

    session_id = f"sess_graph_{uuid.uuid4().hex[:8]}"

    # Seed mock node & edge vào SQLite
    async def seed_graph():
        container = await get_container()
        # Tạo session trước để thỏa mãn FK
        await container.session_repository.create(
            session_id=session_id,
            name="Graph Test Session",
            target="https://api.test/graph",
        )
        n1 = GraphNode(
            id=f"node_req_{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            node_type=NodeType.HTTP_REQUEST,
            label="GET /api/test",
            entity_id="req_01",
            properties={"url": "https://api.test/graph", "method": "GET"},
            created_at_ns=1000,
        )
        n2 = GraphNode(
            id=f"node_crypto_{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            node_type=NodeType.CRYPTO_OPERATION,
            label="HMAC-SHA256",
            properties={"algorithm": "HMAC"},
            created_at_ns=1010,
        )
        e1 = GraphEdge(
            id=1,
            session_id=session_id,
            source_id=n2.id,
            target_id=n1.id,
            relation_type=RelationType.TRANSFORMS,
            confidence=0.95,
            provenance_status="VERIFIED",
            properties={},
            created_at_ns=1020,
        )
        await container.graph_repository.save_nodes([n1, n2])
        await container.graph_repository.save_edges([e1])
        return n1.id, n2.id

    node_req_id, node_crypto_id = asyncio.run(seed_graph())

    # 1. GET /api/graph/{session_id}
    res = client.get(f"/api/graph/{session_id}")
    assert res.status_code == 200
    graph_data = res.json()
    assert len(graph_data["nodes"]) == 2
    assert len(graph_data["edges"]) == 1

    # 2. PATCH alias
    res_alias = client.patch(
        f"/api/graph/{session_id}/nodes/{node_crypto_id}/alias",
        json={"alias": "MyHmacSigner"},
    )
    assert res_alias.status_code == 200
    assert res_alias.json()["alias"] == "MyHmacSigner"

    # Kiểm tra lại sau khi đổi alias
    res_after_alias = client.get(f"/api/graph/{session_id}")
    node_crypto = next(n for n in res_after_alias.json()["nodes"] if n["id"] == node_crypto_id)
    assert node_crypto["alias"] == "MyHmacSigner"

    # 3. DELETE node
    res_del = client.delete(f"/api/graph/{session_id}/nodes/{node_crypto_id}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # Kiểm tra node và edge liên quan đã bị cascade xóa
    res_after_del = client.get(f"/api/graph/{session_id}")
    remaining_nodes = res_after_del.json()["nodes"]
    assert len(remaining_nodes) == 1
    assert remaining_nodes[0]["id"] == node_req_id
    assert len(res_after_del.json()["edges"]) == 0


def test_evolution_api(client: TestClient):
    """Kiểm tra Evolution & Retrospective APIs."""
    import asyncio
    import uuid
    from playground.backend.dependencies import get_container

    task_id = f"task_evo_{uuid.uuid4().hex[:8]}"

    async def seed_retro():
        container = await get_container()
        await container.create_task_uc.execute(
            task_id=task_id,
            name="Evolution Test Task",
            goal_description="Evaluate tool proposals",
        )
        await container.record_retrospective_uc.execute(
            task_id=task_id,
            agent_evaluation="Need better SubtleCrypto hooks.",
            missing_tools=["mcp_crypto_dumper"],
            suggested_tools=[
                {
                    "name": "crypto_key_dump",
                    "purpose": "Dump subtle keys",
                    "parameters": {"algo": "string"},
                }
            ],
            efficiency_rating=9.0,
        )

    asyncio.run(seed_retro())

    # 1. GET /api/evolution/summary
    res_sum = client.get(f"/api/evolution/summary?task_id={task_id}")
    assert res_sum.status_code == 200
    summary = res_sum.json()
    assert summary["total_retrospectives"] >= 1
    assert summary["average_efficiency_rating"] > 0
    assert any(t["tool"] == "mcp_crypto_dumper" for t in summary["top_missing_tools"])

    # 2. GET /api/evolution/logs/{task_id}
    res_logs = client.get(f"/api/evolution/logs/{task_id}")
    assert res_logs.status_code == 200
    logs = res_logs.json()
    assert len(logs) >= 1
    assert logs[0]["task_id"] == task_id
    assert logs[0]["efficiency_rating"] == 5
