import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.graph.project_session_graph import ProjectSessionGraphUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.generate_replay_spec import GenerateReplaySpecUseCase
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.domain.lineage.entities import ParameterType
from app.domain.trace.value_objects import CookieSeed, PreSeedState, StorageSeed


class MockWebHandler(BaseHTTPRequestHandler):
    """Mock HTTP Server phục vụ test Phase 2."""

    def do_GET(self):
        html = b"<!DOCTYPE html><html><body>Profile Page</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        resp_data = json.dumps({"success": True, "code": 0}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(resp_data)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockWebHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_phase2_graph_projection_and_lineage(mock_server):
    # 1. Khởi tạo toàn bộ các Use Case từ Phase 1 và Phase 2
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)

    ingest_use_case = IngestEventUseCase(event_store=event_repo)
    start_use_case = StartSessionUseCase(session_repository=session_repo, ingest_use_case=ingest_use_case)
    stop_use_case = StopSessionUseCase(session_repository=session_repo, active_browsers=start_use_case.active_browsers)

    project_graph_use_case = ProjectSessionGraphUseCase(graph_repository=graph_repo, session_factory=AsyncSessionLocal)
    trace_lineage_use_case = TraceLineageUseCase(graph_repository=graph_repo)
    diff_use_case = DifferentialAnalysisUseCase(session_repository=session_repo, session_factory=AsyncSessionLocal)
    replay_spec_use_case = GenerateReplaySpecUseCase(
        graph_repository=graph_repo,
        diff_use_case=diff_use_case,
        trace_use_case=trace_lineage_use_case,
        session_factory=AsyncSessionLocal,
    )

    task_id = f"task_p2_{uuid.uuid4().hex[:8]}"

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 1: Thu thập Session 1 & Session 2 (Phase 1 handover)
    # ═══════════════════════════════════════════════════════════════════════
    # Session 1: Đổi tên thành "Le Van Mot"
    s1_id = f"sess_p2_1_{uuid.uuid4().hex[:8]}"
    seed_1 = PreSeedState(
        cookies=[CookieSeed(name="uid", value="101", domain="127.0.0.1")],
        storage=StorageSeed(local_storage={"auth_token": "token_SESS_1", "device": "dev_A"}),
    )
    await start_use_case.execute(session_id=s1_id, name="Sess 1", target=mock_server, task_id=task_id, pre_seed_state=seed_1, options={"headless": True})
    p1 = start_use_case.active_browsers[s1_id].page
    assert p1 is not None

    await p1.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            await fetch("{mock_server}/api/account/update", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json", "Authorization": "Bearer " + token }},
                body: JSON.stringify({{ name: "Le Van Mot", timestamp: Date.now() }})
            }});
        }}"""
    )
    await asyncio.sleep(0.5)
    await stop_use_case.execute(s1_id)

    # Session 2: Đổi tên thành "Pham Van Hai"
    s2_id = f"sess_p2_2_{uuid.uuid4().hex[:8]}"
    seed_2 = PreSeedState(
        cookies=[CookieSeed(name="uid", value="102", domain="127.0.0.1")],
        storage=StorageSeed(local_storage={"auth_token": "token_SESS_2", "device": "dev_A"}),
    )
    await start_use_case.execute(session_id=s2_id, name="Sess 2", target=mock_server, task_id=task_id, pre_seed_state=seed_2, options={"headless": True})
    p2 = start_use_case.active_browsers[s2_id].page
    assert p2 is not None

    await p2.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            await fetch("{mock_server}/api/account/update", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json", "Authorization": "Bearer " + token }},
                body: JSON.stringify({{ name: "Pham Van Hai", timestamp: Date.now() }})
            }});
        }}"""
    )
    await asyncio.sleep(0.5)
    await stop_use_case.execute(s2_id)

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 2: Chiếu đồ thị (Graph Projection) cho cả 2 session
    # ═══════════════════════════════════════════════════════════════════════
    res_graph_1 = await project_graph_use_case.execute(s1_id)
    assert res_graph_1["nodes_count"] > 0
    assert res_graph_1["edges_count"] > 0

    res_graph_2 = await project_graph_use_case.execute(s2_id)
    assert res_graph_2["nodes_count"] > 0
    assert res_graph_2["edges_count"] > 0

    nodes_s1 = await graph_repo.get_nodes(s1_id)
    edges_s1 = await graph_repo.get_edges(s1_id)

    node_types_s1 = [n.node_type for n in nodes_s1]
    assert NodeType.SESSION.value in node_types_s1
    assert NodeType.HTTP_REQUEST.value in node_types_s1
    assert NodeType.STORAGE_ENTRY.value in node_types_s1

    rel_types_s1 = [e.relation_type for e in edges_s1]
    assert RelationType.CONTAINS.value in rel_types_s1
    assert RelationType.READS_FROM.value in rel_types_s1 or RelationType.USED_IN.value in rel_types_s1

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 3: Lineage Analysis (Backward & Forward Trace)
    # ═══════════════════════════════════════════════════════════════════════
    # Lấy request POST
    req_post_s1 = [n for n in nodes_s1 if n.node_type == NodeType.HTTP_REQUEST.value and "POST" in (n.label or "")][0]

    # Truy vết backward cho request POST
    backward_path = await trace_lineage_use_case.trace_backward(
        session_id=s1_id,
        target_node_id=req_post_s1.id,
        param_name="auth_token",
    )
    assert backward_path is not None
    assert backward_path.origin_type in ["storage", "user_input_or_constant"]
    assert len(backward_path.steps) > 0
    assert backward_path.steps[0].confidence >= 0.9

    # Truy vết forward từ node storage
    storage_nodes = [n for n in nodes_s1 if n.node_type == NodeType.STORAGE_ENTRY.value]
    assert len(storage_nodes) > 0
    forward_paths = await trace_lineage_use_case.trace_forward(
        session_id=s1_id,
        origin_node_id=storage_nodes[0].id,
    )
    assert len(forward_paths) > 0
    assert forward_paths[0].target_node_id == req_post_s1.id

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 4: Differential Analysis (So sánh đa phiên theo Task)
    # ═══════════════════════════════════════════════════════════════════════
    diff_result = await diff_use_case.execute(task_id)
    assert len(diff_result.session_ids) == 2
    assert "body.name" in diff_result.classified_variables
    assert any("authorization" in t or "auth_token" in t for t in diff_result.classified_tokens)

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 5: Handover to Phase 3 (ReplaySpec Generation)
    # ═══════════════════════════════════════════════════════════════════════
    replay_spec = await replay_spec_use_case.execute(
        task_id=task_id,
        target_request_id=req_post_s1.entity_id or req_post_s1.id,
    )
    assert replay_spec.task_id == task_id
    assert replay_spec.method == "POST"
    assert "name" in replay_spec.required_variables
    assert "{{name}}" in str(replay_spec.body_template)
    assert "{{auth_token}}" in str(replay_spec.headers_template)
    assert len(replay_spec.session_prerequisites) > 0
    assert replay_spec.session_prerequisites[0].step_type == "read_storage"
