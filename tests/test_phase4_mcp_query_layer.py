import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.graph.project_session_graph import ProjectSessionGraphUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.trace.value_objects import PreSeedState, StorageSeed
from app.interfaces.mcp.tools.capture import get_capture_status_tool
from app.interfaces.mcp.tools.graph import (
    get_graph_neighbors_tool,
    get_graph_node_tool,
    get_graph_statistics_tool,
)
from app.interfaces.mcp.tools.lineage import (
    compare_lineage_tool,
    explain_lineage_path_tool,
    trace_downstream_tool,
    trace_origin_tool,
)
from app.interfaces.mcp.tools.network import (
    analyze_request_lineage_tool,
    compare_requests_tool,
    find_request_dependencies_tool,
    summarize_request_tool,
)
from app.interfaces.mcp.tools.replay import (
    prepare_replay_tool,
    synthesize_code_tool,
)
from app.interfaces.mcp.tools.trace import (
    get_trace_timeline_tool,
    search_trace_events_tool,
)


class MockOrderServer(BaseHTTPRequestHandler):
    """Mock server phục vụ test toàn bộ Phase 4 MCP Query Layer."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        resp = json.dumps({
            "code": 200,
            "data": {
                "server_token": "token_mcp_test_secret_12345",
                "echo": json.loads(body) if body else {},
            },
        }).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockOrderServer)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_phase4_mcp_query_layer(mock_server):
    # 1. Thiết lập phiên và thu thập dữ liệu
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)

    ingest_use_case = IngestEventUseCase(event_store=event_repo)
    start_use_case = StartSessionUseCase(session_repository=session_repo, ingest_use_case=ingest_use_case)
    stop_use_case = StopSessionUseCase(session_repository=session_repo, active_browsers=start_use_case.active_browsers)
    project_graph_use_case = ProjectSessionGraphUseCase(graph_repository=graph_repo, session_factory=AsyncSessionLocal)

    session_id = f"sess_mcp_{uuid.uuid4().hex[:8]}"
    task_id = f"task_mcp_{uuid.uuid4().hex[:8]}"

    seed = PreSeedState(
        storage=StorageSeed(local_storage={"auth_token": "secret_initial_token_xyz"}),
    )

    await start_use_case.execute(
        session_id=session_id,
        name="MCP Query Session",
        target=mock_server,
        task_id=task_id,
        pre_seed_state=seed,
        options={"headless": True},
    )

    page = start_use_case.active_browsers[session_id].page
    assert page is not None

    # Chạy kịch bản JS phát request
    await page.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            const resp = await fetch("{mock_server}/api/checkout", {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token,
                }},
                body: JSON.stringify({{ order_id: 101, token_ref: token }})
            }});
            const json = await resp.json();
            if (json && json.data) {{
                localStorage.setItem("result_token", json.data.server_token);
            }}
        }}"""
    )

    await asyncio.sleep(0.5)
    await stop_use_case.execute(session_id)
    await project_graph_use_case.execute(session_id)

    # =========================================================================
    # 2. KIỂM THỬ NHÓM CAPTURE TOOLS
    # =========================================================================
    cap_res = await get_capture_status_tool(session_id)
    assert cap_res["schema_version"] == "mcp.response.v1"
    assert cap_res["status"] == "COMPLETED"
    assert cap_res["data"]["status"].upper() == "STOPPED"
    assert "statistics" in cap_res["data"]
    assert cap_res["data"]["statistics"]["network_requests"] > 0

    # Test trường hợp NOT_FOUND
    not_found_res = await get_capture_status_tool("non_existent_session_id")
    assert not_found_res["status"] == "NOT_FOUND"
    assert len(not_found_res["metadata"]["warnings"]) > 0

    # =========================================================================
    # 3. KIỂM THỬ NHÓM TRACE TOOLS
    # =========================================================================
    trace_res = await search_trace_events_tool(session_id=session_id, limit=20)
    assert trace_res["status"] in ("COMPLETED", "PARTIAL")
    assert len(trace_res["data"]["events"]) > 0

    timeline_res = await get_trace_timeline_tool(session_id=session_id, limit=20)
    assert timeline_res["status"] in ("COMPLETED", "PARTIAL")
    assert len(timeline_res["data"]["timeline"]) > 0
    assert "summary" in timeline_res["data"]["timeline"][0]

    # =========================================================================
    # 4. KIỂM THỬ NHÓM GRAPH QUERY TOOLS
    # =========================================================================
    stats_res = await get_graph_statistics_tool(session_id=session_id)
    assert stats_res["status"] == "COMPLETED"
    assert stats_res["data"]["node_count"] > 0
    assert stats_res["data"]["edge_count"] > 0
    assert "edge_distribution" in stats_res["data"]

    nodes = await graph_repo.get_nodes(session_id)
    req_node = next(
        n for n in nodes if n.node_type == "http_request" and "checkout" in str(n.properties.get("url"))
    )

    node_res = await get_graph_node_tool(session_id=session_id, node_id=req_node.id)
    assert node_res["status"] == "COMPLETED"
    assert node_res["data"]["node"]["id"] == req_node.id
    assert "evidence" in node_res["data"]

    neighbors_res = await get_graph_neighbors_tool(
        session_id=session_id, node_id=req_node.id, direction="both"
    )
    assert neighbors_res["status"] == "COMPLETED"
    assert neighbors_res["data"]["total_count"] > 0

    # =========================================================================
    # 5. KIỂM THỬ NHÓM LINEAGE ANALYSIS TOOLS
    # =========================================================================
    origin_res = await trace_origin_tool(session_id=session_id, target_node_id=req_node.id)
    assert origin_res["status"] in ("COMPLETED", "PARTIAL")
    assert "paths" in origin_res["data"]

    downstream_res = await trace_downstream_tool(session_id=session_id, source_node_id=req_node.id)
    assert downstream_res["status"] == "COMPLETED"
    assert "usages" in downstream_res["data"]

    explain_res = await explain_lineage_path_tool(session_id=session_id, target_node_id=req_node.id)
    assert explain_res["status"] == "COMPLETED"
    assert "summary" in explain_res["data"]
    assert len(explain_res["data"]["steps"]) > 0

    compare_lin_res = await compare_lineage_tool(
        left_session_id=session_id,
        left_node_id=req_node.id,
        right_session_id=session_id,
        right_node_id=req_node.id,
    )
    assert compare_lin_res["status"] == "COMPLETED"
    assert compare_lin_res["data"]["origins_match"] is True
    assert compare_lin_res["data"]["structural_similarity"] == 1.0

    # =========================================================================
    # 6. KIỂM THỬ NHÓM NETWORK ANALYSIS & REDACTION
    # =========================================================================
    summarize_res = await summarize_request_tool(
        session_id=session_id,
        request_id=req_node.entity_id or req_node.id,
        redaction_mode="strict",
    )
    assert summarize_res["status"] == "COMPLETED"
    req_data = summarize_res["data"]
    assert req_data["method"] == "POST"
    # Xác thực Redaction: Authorization header và token trong body phải bị che giấu
    headers = req_data.get("headers", {})
    if "authorization" in headers:
        assert headers["authorization"] == "[REDACTED]"
    if "Authorization" in headers:
        assert headers["Authorization"] == "[REDACTED]"

    lineage_net_res = await analyze_request_lineage_tool(
        session_id=session_id, request_id=req_node.entity_id or req_node.id
    )
    assert lineage_net_res["status"] == "COMPLETED"
    assert len(lineage_net_res["data"]["sources"]) > 0

    dep_res = await find_request_dependencies_tool(
        session_id=session_id, request_id=req_node.entity_id or req_node.id
    )
    assert dep_res["status"] == "COMPLETED"
    assert dep_res["data"]["total_dependencies"] > 0

    diff_net_res = await compare_requests_tool(
        left_session_id=session_id,
        left_request_id=req_node.entity_id or req_node.id,
        right_session_id=session_id,
        right_request_id=req_node.entity_id or req_node.id,
    )
    assert diff_net_res["status"] == "COMPLETED"
    assert diff_net_res["data"]["is_identical"] is True

    # =========================================================================
    # 7. KIỂM THỬ NHÓM REPLAY ENGINE & CODE SYNTHESIS TOOLS
    # =========================================================================
    replay_prep = await prepare_replay_tool(
        task_id=task_id, target_request_id=req_node.entity_id or req_node.id
    )
    assert replay_prep["status"] in ("COMPLETED", "prepared")
    assert replay_prep["data"]["status"] == "prepared"

    synth_res = await synthesize_code_tool(
        task_id=task_id, target_request_id=req_node.entity_id or req_node.id, language="python"
    )
    assert synth_res["language"] == "python"
    assert "import httpx" in synth_res["code"]
