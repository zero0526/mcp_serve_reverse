import time
import uuid
import pytest
from sqlalchemy import select

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.adapters.persistence.sqlite.models import GraphNodeModel, GraphEdgeModel
from app.application.graph.compact_graph import CompactGraphUseCase
from app.application.graph.project_event import ProjectEventUseCase
from app.application.graph.rebuild_graph import RebuildGraphUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.graph.edges import GraphEdge
from app.domain.graph.nodes import GraphNode, NodeType
from app.domain.graph.relations import RelationType
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope


@pytest.mark.asyncio
async def test_streaming_event_projection():
    """Kiểm thử chiếu tức thì từng event vào Property Graph ngay khi ingest (ProjectEventUseCase)."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    project_event_uc = ProjectEventUseCase(graph_repository=graph_repo)

    session_id = f"sess_stream_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Stream Test", target="https://example.com")

    # 1. Chiếu Request Event
    stream_req_id = f"req_login_{uuid.uuid4().hex[:8]}"
    req_envelope = EventEnvelope(
        event_id=f"evt_req_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=time.time_ns(),
        execution_id="exec_caller_123",
        payload={
            "request_id": stream_req_id,
            "method": "POST",
            "url": "https://api.example.com/login",
            "headers": {"content-type": "application/json"},
            "body": '{"username": "admin"}',
        },
        metadata={"function_name": "onLoginSubmit"},
    )
    res_req = await project_event_uc.execute(req_envelope)
    assert res_req["nodes_projected"] >= 2  # Session, Request, Caller Function
    assert res_req["edges_projected"] >= 2

    # 2. Chiếu Response Event
    res_envelope = EventEnvelope(
        event_id=f"evt_res_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_RESPONSE,
        timestamp_ns=time.time_ns(),
        payload={
            "request_id": stream_req_id,
            "status_code": 200,
            "body": '{"token": "jwt_secret_xyz"}',
        },
    )
    res_res = await project_event_uc.execute(res_envelope)
    assert res_res["nodes_projected"] >= 1  # Response node
    assert res_res["edges_projected"] >= 1  # Associated with request

    # 3. Chiếu Crypto Operation Event
    crypto_envelope = EventEnvelope(
        event_id=f"evt_cry_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.CRYPTO_OPERATION,
        timestamp_ns=time.time_ns(),
        payload={
            "operation_id": "cry_sha256_pass",
            "algorithm": "SHA-256",
            "input_hash": "raw_pass_hash",
            "output_hash": "encrypted_pass_hash",
        },
    )
    res_cry = await project_event_uc.execute(crypto_envelope)
    assert res_cry["nodes_projected"] >= 1

    # Kiểm tra database SQLite: các node và edge đã được lưu trực tiếp
    nodes = await graph_repo.get_nodes(session_id)
    edges = await graph_repo.get_edges(session_id)

    node_types = {n.node_type for n in nodes}
    edge_types = {e.relation_type for e in edges}

    assert NodeType.SESSION.value in node_types
    assert NodeType.HTTP_REQUEST.value in node_types
    assert NodeType.HTTP_RESPONSE.value in node_types
    assert NodeType.FUNCTION_EXECUTION.value in node_types
    assert NodeType.CRYPTO_OPERATION.value in node_types

    assert RelationType.CONTAINS.value in edge_types
    assert RelationType.CALLS.value in edge_types
    assert RelationType.ASSOCIATED_WITH.value in edge_types


@pytest.mark.asyncio
async def test_rebuild_graph_from_trace_events():
    """Kiểm thử xóa và tái tạo toàn bộ đồ thị từ trace events (RebuildGraphUseCase)."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)
    rebuild_uc = RebuildGraphUseCase(graph_repository=graph_repo)

    session_id = f"sess_rebuild_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Rebuild Test", target="https://example.com")

    # Ingest 2 events vào SQLite Event Store
    evt1 = EventEnvelope(
        event_id=f"evt_r1_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.STORAGE_WRITE,
        timestamp_ns=time.time_ns(),
        payload={"storage_type": "local_storage", "storage_key": "auth_token", "value_preview": "tok_123"},
    )
    rebuild_req_id = f"req_rebuild_{uuid.uuid4().hex[:8]}"
    evt2 = EventEnvelope(
        event_id=f"evt_r2_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=time.time_ns(),
        payload={
            "request_id": rebuild_req_id,
            "method": "GET",
            "url": "https://api.example.com/user/profile",
            "headers": {"authorization": "Bearer tok_123"},
        },
    )
    await ingest_uc.execute(evt1)
    await ingest_uc.execute(evt2)

    # Chạy Rebuild
    res = await rebuild_uc.execute(session_id)
    assert res["status"] == "rebuilt"
    assert res["nodes_count"] >= 3  # Session, StorageEntry, Request
    assert res["edges_count"] >= 2  # CONTAINS, READS_FROM (lineage inference)

    # Kiểm tra nodes trong database
    nodes = await graph_repo.get_nodes(session_id)
    labels = [n.label for n in nodes]
    assert any("local_storage.auth_token" in l for l in labels)
    assert any("GET /user/profile" in l for l in labels)


@pytest.mark.asyncio
async def test_compact_graph_and_pruning():
    """Kiểm thử thuật toán cắt tỉa nhiễu và rút gọn đồ thị (CompactGraphUseCase)."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
    compact_uc = CompactGraphUseCase(graph_repository=graph_repo)

    session_id = f"sess_compact_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Compact Test", target="https://example.com")
    sess_node_id = f"node_sess_{session_id}"

    # Tạo các node thủ công:
    # 1. Session node
    # 2. Node API request (hợp lệ - cần giữ)
    # 3. Node Static request logo.png (nhiễu - cần cắt tỉa)
    # 4. Node Framework internal __webpack_require__ (nhiễu - cần cắt tỉa)
    # 5. Node Isolated storage entry (nhiễu - cần cắt tỉa)
    nodes = [
        GraphNode(id=sess_node_id, session_id=session_id, node_type=NodeType.SESSION, label="Session"),
        GraphNode(
            id=f"node_req_api_{session_id}",
            session_id=session_id,
            node_type=NodeType.HTTP_REQUEST,
            label="POST /api/checkout",
            properties={"url": "https://app.com/api/checkout"},
        ),
        GraphNode(
            id=f"node_req_static_{session_id}",
            session_id=session_id,
            node_type=NodeType.HTTP_REQUEST,
            label="GET /assets/logo.png",
            properties={"url": "https://app.com/assets/logo.png"},
        ),
        GraphNode(
            id=f"node_fn_internal_{session_id}",
            session_id=session_id,
            node_type=NodeType.FUNCTION_EXECUTION,
            label="__webpack_require__",
            properties={"function_name": "__webpack_require__"},
        ),
        GraphNode(
            id=f"node_stor_isolated_{session_id}",
            session_id=session_id,
            node_type=NodeType.STORAGE_ENTRY,
            label="local_storage.unused_key",
            properties={"storage_key": "unused_key"},
        ),
    ]

    edges = [
        GraphEdge(session_id=session_id, source_id=sess_node_id, target_id=nodes[1].id, relation_type=RelationType.CONTAINS),
        GraphEdge(session_id=session_id, source_id=sess_node_id, target_id=nodes[2].id, relation_type=RelationType.CONTAINS),
        GraphEdge(session_id=session_id, source_id=sess_node_id, target_id=nodes[3].id, relation_type=RelationType.CONTAINS),
        GraphEdge(session_id=session_id, source_id=sess_node_id, target_id=nodes[4].id, relation_type=RelationType.CONTAINS),
    ]

    await graph_repo.save_nodes(nodes)
    await graph_repo.save_edges(edges)

    # Chạy Compaction
    res = await compact_uc.execute(session_id)
    assert res["status"] == "compacted"
    assert res["pruned_nodes_count"] >= 3  # logo.png, __webpack_require__, unused_key

    # Kiểm tra nodes còn lại
    remaining_nodes = await graph_repo.get_nodes(session_id)
    remaining_ids = {n.id for n in remaining_nodes}

    assert sess_node_id in remaining_ids
    assert nodes[1].id in remaining_ids  # API request checkout được giữ lại
    assert nodes[2].id not in remaining_ids  # logo.png bị xóa
    assert nodes[3].id not in remaining_ids  # __webpack_require__ bị xóa
    assert nodes[4].id not in remaining_ids  # isolated storage node bị xóa
