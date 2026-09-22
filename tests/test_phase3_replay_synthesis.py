import ast
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
from app.adapters.replay.http_client import HttpxReplayExecutor
from app.adapters.synthesis.code_synthesizer import CodeSynthesizer
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.graph.project_session_graph import ProjectSessionGraphUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.generate_replay_spec import GenerateReplaySpecUseCase
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.application.replay.compare_responses import CompareResponsesUseCase
from app.application.replay.execute_replay import ExecuteReplayUseCase
from app.application.replay.prepare_replay import PrepareReplayUseCase
from app.application.replay.synthesize_code import SynthesizeCodeUseCase
from app.domain.graph.nodes import NodeType
from app.domain.replay.entities import ReplayMode
from app.domain.replay.policies import ReplaySafetyPolicy, VariableResolver
from app.domain.trace.value_objects import PreSeedState, StorageSeed
from app.interfaces.mcp.tools.replay import (
    execute_replay_tool,
    prepare_replay_tool,
    synthesize_code_tool,
)


class MockEchoServer(BaseHTTPRequestHandler):
    """Mock HTTP Server phục vụ test Replay Engine."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(length).decode("utf-8")
        auth_header = self.headers.get("Authorization", "")

        resp_data = json.dumps({
            "success": True,
            "code": 0,
            "echo": json.loads(req_body) if req_body else {},
            "auth": auth_header,
        }).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(resp_data)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def echo_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockEchoServer)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_phase3_replay_engine_and_code_synthesis(echo_server):
    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 1: Thu thập và tạo dữ liệu baseline (Phase 1 & Phase 2)
    # ═══════════════════════════════════════════════════════════════════════
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)

    ingest_use_case = IngestEventUseCase(event_store=event_repo)
    start_use_case = StartSessionUseCase(session_repository=session_repo, ingest_use_case=ingest_use_case)
    stop_use_case = StopSessionUseCase(session_repository=session_repo, active_browsers=start_use_case.active_browsers)

    project_graph_use_case = ProjectSessionGraphUseCase(graph_repository=graph_repo, session_factory=AsyncSessionLocal)
    trace_lineage_use_case = TraceLineageUseCase(graph_repository=graph_repo)
    diff_use_case = DifferentialAnalysisUseCase(session_factory=AsyncSessionLocal)
    replay_spec_use_case = GenerateReplaySpecUseCase(
        graph_repository=graph_repo,
        diff_use_case=diff_use_case,
        trace_use_case=trace_lineage_use_case,
        session_factory=AsyncSessionLocal,
    )

    task_id = f"task_p3_{uuid.uuid4().hex[:8]}"

    # Chạy Session 1: Pre-seed token và gửi POST request
    s1_id = f"sess_p3_1_{uuid.uuid4().hex[:8]}"
    seed_1 = PreSeedState(
        storage=StorageSeed(local_storage={"auth_token": "secret_token_12345"}),
    )
    await start_use_case.execute(
        session_id=s1_id,
        name="Sess 1",
        target=echo_server,
        task_id=task_id,
        pre_seed_state=seed_1,
        options={"headless": True},
    )
    p1 = start_use_case.active_browsers[s1_id].page
    assert p1 is not None
    await p1.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            await fetch("{echo_server}/api/order", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json", "Authorization": "Bearer " + token }},
                body: JSON.stringify({{ name: "Nguyen Van A", timestamp: Date.now() }})
            }});
        }}"""
    )
    await asyncio.sleep(0.5)
    await stop_use_case.execute(s1_id)

    # Chạy Session 2: Phục vụ vi phân
    s2_id = f"sess_p3_2_{uuid.uuid4().hex[:8]}"
    seed_2 = PreSeedState(
        storage=StorageSeed(local_storage={"auth_token": "secret_token_12345"}),
    )
    await start_use_case.execute(
        session_id=s2_id,
        name="Sess 2",
        target=echo_server,
        task_id=task_id,
        pre_seed_state=seed_2,
        options={"headless": True},
    )
    p2 = start_use_case.active_browsers[s2_id].page
    assert p2 is not None
    await p2.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            await fetch("{echo_server}/api/order", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json", "Authorization": "Bearer " + token }},
                body: JSON.stringify({{ name: "Tran Van B", timestamp: Date.now() }})
            }});
        }}"""
    )
    await asyncio.sleep(0.5)
    await stop_use_case.execute(s2_id)

    # Chiếu đồ thị
    await project_graph_use_case.execute(s1_id)
    await project_graph_use_case.execute(s2_id)

    # Lấy node POST request của session 1
    nodes_s1 = await graph_repo.get_nodes(s1_id)
    post_node = [n for n in nodes_s1 if n.node_type == NodeType.HTTP_REQUEST.value and "POST" in (n.label or "")][0]
    target_req_id = post_node.entity_id or post_node.id

    # Sinh ReplaySpec từ Phase 2
    spec = await replay_spec_use_case.execute(task_id, target_req_id)
    assert spec.method == "POST"
    assert "name" in spec.required_variables

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 2: Kiểm thử Prepare Replay (Substitution & Interpolation)
    # ═══════════════════════════════════════════════════════════════════════
    prepare_uc = PrepareReplayUseCase()
    prepared_req = prepare_uc.execute(
        spec=spec,
        variables={"auth_token": "replay_bearer_token", "name": "Le Thi C"},
    )
    assert prepared_req.method == "POST"
    assert prepared_req.headers.get("Authorization") == "Bearer replay_bearer_token"
    assert prepared_req.body["name"] == "Le Thi C"
    # timestamp được giải quyết tự động
    assert isinstance(prepared_req.body["timestamp"], (int, float))

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 3: Kiểm thử Replay Modes (DRY_RUN & EXECUTE & Comparison)
    # ═══════════════════════════════════════════════════════════════════════
    executor = HttpxReplayExecutor()
    compare_uc = CompareResponsesUseCase()
    execute_uc = ExecuteReplayUseCase(
        http_executor=executor,
        prepare_use_case=prepare_uc,
        compare_use_case=compare_uc,
        session_factory=AsyncSessionLocal,
    )

    # 3.1. Chế độ DRY_RUN: không phát sinh request mạng
    dry_req, dry_res, dry_comp = await execute_uc.execute(
        spec=spec,
        variables={"auth_token": "token_dry_run", "name": "Pham Van Dry"},
        mode=ReplayMode.DRY_RUN,
    )
    assert dry_req is not None
    assert dry_res is None
    assert dry_comp is None

    # 3.2. Chế độ EXECUTE: phát lại request thực tế và so sánh với baseline
    live_req, live_res, live_comp = await execute_uc.execute(
        spec=spec,
        variables={"auth_token": "token_live_test", "name": "Hoang Van Real"},
        mode=ReplayMode.EXECUTE,
    )
    assert live_res is not None
    assert live_res.status_code == 200
    assert live_res.success is True
    assert live_res.latency_ms >= 0.0
    assert live_res.body["auth"] == "Bearer token_live_test"
    assert live_res.body["echo"]["name"] == "Hoang Van Real"

    assert live_comp is not None
    assert live_comp.status_match is True
    assert live_comp.expected_status == 200
    assert live_comp.actual_status == 200
    assert live_comp.match_score >= 0.7

    # 3.3. Kiểm thử Safety Policy: chặn URL không được cho phép
    strict_policy = ReplaySafetyPolicy(allowed_hosts=["untrusted-domain.invalid"])
    blocked_res = await executor.execute(prepared_req, policy=strict_policy)
    assert blocked_res.status_code == 403
    assert blocked_res.success is False
    assert "safety policy" in (blocked_res.error_message or "")

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 4: Kiểm thử Code Synthesis (Python, cURL, TypeScript)
    # ═══════════════════════════════════════════════════════════════════════
    synthesizer = CodeSynthesizer()
    synth_uc = SynthesizeCodeUseCase(
        generate_spec_use_case=replay_spec_use_case,
        synthesizer=synthesizer,
    )

    # 4.1. Sinh mã Python
    py_code_res = await synth_uc.execute(
        task_id=task_id,
        target_request_id=target_req_id,
        language="python",
        spec=spec,
    )
    assert py_code_res.language == "python"
    assert "async def execute_request" in py_code_res.code
    assert "httpx.AsyncClient" in py_code_res.code
    assert "name: Any" in py_code_res.code

    # Xác thực cú pháp Python sinh ra hoàn toàn hợp lệ (không lỗi AST)
    parsed_ast = ast.parse(py_code_res.code)
    assert parsed_ast is not None

    # 4.2. Sinh lệnh cURL
    curl_res = await synth_uc.execute(
        task_id=task_id,
        target_request_id=target_req_id,
        language="curl",
        spec=spec,
    )
    assert curl_res.language == "curl"
    assert "curl -X POST" in curl_res.code
    assert "-H 'Content-Type: application/json'" in curl_res.code
    assert "-d '{" in curl_res.code

    # 4.3. Sinh mã TypeScript
    ts_res = await synth_uc.execute(
        task_id=task_id,
        target_request_id=target_req_id,
        language="typescript",
        spec=spec,
    )
    assert ts_res.language == "typescript"
    assert "export interface ExecuteRequestParams" in ts_res.code
    assert "export async function executeRequest" in ts_res.code
    assert "name: any;" in ts_res.code

    # ═══════════════════════════════════════════════════════════════════════
    # BƯỚC 5: Kiểm thử MCP Tools Interface
    # ═══════════════════════════════════════════════════════════════════════
    tool_prep = await prepare_replay_tool(
        task_id=task_id,
        target_request_id=target_req_id,
        variables={"name": "MCP User"},
    )
    assert tool_prep["status"] == "prepared"
    assert tool_prep["request"]["method"] == "POST"

    tool_dry = await execute_replay_tool(
        task_id=task_id,
        target_request_id=target_req_id,
        variables={"name": "MCP Dry"},
        mode="dry_run",
    )
    assert tool_dry["mode"] == "dry_run"
    assert tool_dry["execution_result"] is None

    tool_synth = await synthesize_code_tool(
        task_id=task_id,
        target_request_id=target_req_id,
        language="python",
    )
    assert tool_synth["language"] == "python"
    assert "async def execute_request" in tool_synth["code"]
