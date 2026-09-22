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
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.domain.trace.value_objects import PreSeedState, StorageSeed


class MockServer(BaseHTTPRequestHandler):
    """Mock server trả về JSON payload phục vụ kiểm thử pre/post response tracking."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        resp = json.dumps({
            "code": 200,
            "data": {
                "server_token": "token_from_server_999",
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockServer)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_pre_and_post_request_function_graph(mock_server):
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)

    ingest_use_case = IngestEventUseCase(event_store=event_repo)
    start_use_case = StartSessionUseCase(session_repository=session_repo, ingest_use_case=ingest_use_case)
    stop_use_case = StopSessionUseCase(session_repository=session_repo, active_browsers=start_use_case.active_browsers)
    project_graph_use_case = ProjectSessionGraphUseCase(graph_repository=graph_repo, session_factory=AsyncSessionLocal)

    session_id = f"sess_full_{uuid.uuid4().hex[:8]}"
    task_id = f"task_full_{uuid.uuid4().hex[:8]}"

    seed = PreSeedState(
        storage=StorageSeed(local_storage={"device_id": "dev_xyz"}),
    )

    await start_use_case.execute(
        session_id=session_id,
        name="Full Graph Session",
        target=mock_server,
        task_id=task_id,
        pre_seed_state=seed,
        options={"headless": True},
    )

    page = start_use_case.active_browsers[session_id].page
    assert page is not None

    # Kích hoạt chuỗi xử lý JavaScript:
    # 1. Hàm calculateHash (Crypto Subtle digest)
    # 2. Hàm submitOrderData (Chuẩn bị payload & gọi fetch)
    # 3. Hàm handleResponseCallback (Nhận response.json() và đọc data.server_token lưu vào localStorage)
    await page.evaluate(
        f"""async () => {{
            async function calculateHash(text) {{
                const msgUint8 = new TextEncoder().encode(text);
                const hashBuffer = await window.crypto.subtle.digest('SHA-256', msgUint8);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            }}

            async function submitOrderData() {{
                const device = localStorage.getItem("device_id");
                const sign = await calculateHash("order_data_" + device);

                const response = await fetch("{mock_server}/api/order", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json",
                        "X-Signature": sign,
                    }},
                    body: JSON.stringify({{ name: "Antigravity User", device_id: device }})
                }});

                await handleResponseCallback(response);
            }}

            async function handleResponseCallback(resp) {{
                const jsonResult = await resp.json();
                if (jsonResult && jsonResult.data) {{
                    const token = jsonResult.data.server_token;
                    localStorage.setItem("session_token", token);
                }}
            }}

            await submitOrderData();
        }}"""
    )

    await asyncio.sleep(0.8)
    await stop_use_case.execute(session_id)

    # Chiếu đồ thị
    res = await project_graph_use_case.execute(session_id)
    assert res["nodes_count"] > 0
    assert res["edges_count"] > 0

    nodes = await graph_repo.get_nodes(session_id)
    edges = await graph_repo.get_edges(session_id)

    node_types = {n.node_type for n in nodes}
    edge_relations = {e.relation_type for e in edges}

    # 1. Xác thực các node cơ bản
    assert NodeType.SESSION.value in node_types
    assert NodeType.HTTP_REQUEST.value in node_types
    assert NodeType.HTTP_RESPONSE.value in node_types
    assert NodeType.STORAGE_ENTRY.value in node_types

    # 2. Xác thực Pre-request Function Execution Graph
    assert NodeType.FUNCTION_EXECUTION.value in node_types
    fn_nodes = [n for n in nodes if n.node_type == NodeType.FUNCTION_EXECUTION.value]
    fn_names = [n.properties.get("function_name") for n in fn_nodes]
    assert any("submitOrderData" in str(fn) for fn in fn_names)

    # 3. Xác thực Crypto Operations Graph
    assert NodeType.CRYPTO_OPERATION.value in node_types
    crypto_nodes = [n for n in nodes if n.node_type == NodeType.CRYPTO_OPERATION.value]
    assert len(crypto_nodes) > 0
    assert crypto_nodes[0].properties.get("algorithm") == "SHA-256"

    # 4. Xác thực Post-request Response Handling Graph
    # Phải có hàm handleResponseCallback hoặc response consumer
    assert RelationType.CONSUMES.value in edge_relations
    consumes_edges = [e for e in edges if e.relation_type == RelationType.CONSUMES.value]
    assert len(consumes_edges) > 0

    # 5. Xác thực quan hệ lưu trữ Storage
    assert RelationType.STORES_IN.value in edge_relations
    assert RelationType.READS_FROM.value in edge_relations
