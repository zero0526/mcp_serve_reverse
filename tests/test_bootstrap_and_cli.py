import pytest

from app.bootstrap import ApplicationContainer, bootstrap_container
from app.main import create_cli_parser


def test_bootstrap_container_wiring():
    """Kiểm tra Composition Root khởi tạo và kết nối đầy đủ các thành phần."""
    container = bootstrap_container()
    assert isinstance(container, ApplicationContainer)

    # 1. Repositories
    assert container.session_repository is not None
    assert container.event_repository is not None
    assert container.graph_repository is not None

    # 2. Adapters & Guards
    assert container.http_executor is not None
    assert container.redaction_engine is not None
    assert container.graph_projector is not None
    assert container.truncation_guard is not None

    # 3. Use Cases theo 5 Phase
    assert container.start_session_uc is not None
    assert container.stop_session_uc is not None
    assert container.capture_status_uc is not None
    assert container.ingest_event_uc is not None

    assert container.project_event_uc is not None
    assert container.rebuild_graph_uc is not None
    assert container.compact_graph_uc is not None
    assert container.trace_origin_uc is not None
    assert container.trace_downstream_uc is not None
    assert container.find_transformations_uc is not None

    assert container.get_execution_context_uc is not None
    assert container.search_trace_events_uc is not None
    assert container.get_trace_timeline_uc is not None

    assert container.prepare_replay_uc is not None
    assert container.validate_replay_uc is not None
    assert container.resolve_dependencies_uc is not None
    assert container.execute_replay_uc is not None
    assert container.synthesize_code_uc is not None

    # 4. MCP Server
    assert container.mcp_server is not None
    assert len(container.mcp_server._tool_manager._tools) >= 23
    assert len(container.mcp_server._resource_manager._templates) >= 3
    assert len(container.mcp_server._prompt_manager._prompts) >= 3
    assert container.mcp_server.instructions is not None
    assert "Tool Selection Decision Matrix" in container.mcp_server.instructions


def test_cli_parser_subcommands():
    """Kiểm tra parser dòng lệnh nhận diện chính xác các subcommands và flags."""
    parser = create_cli_parser()

    # 1. run-mcp
    args_mcp = parser.parse_args(["run-mcp", "--transport", "stdio"])
    assert args_mcp.command == "run-mcp"
    assert args_mcp.transport == "stdio"

    # 2. capture
    args_cap = parser.parse_args([
        "capture",
        "--target", "https://api.example.com/demo",
        "--name", "Test Session",
        "--headless",
        "--duration", "10",
    ])
    assert args_cap.command == "capture"
    assert args_cap.target == "https://api.example.com/demo"
    assert args_cap.name == "Test Session"
    assert args_cap.headless is True
    assert args_cap.duration == 10

    # 3. replay
    args_rep = parser.parse_args([
        "replay",
        "--session-id", "sess_001",
        "--request-id", "req_002",
        "--mode", "execute",
        "--auto-resolve",
    ])
    assert args_rep.command == "replay"
    assert args_rep.session_id == "sess_001"
    assert args_rep.request_id == "req_002"
    assert args_rep.mode == "execute"
    assert args_rep.auto_resolve is True

    # 4. graph
    args_graph = parser.parse_args([
        "graph",
        "--session-id", "sess_001",
        "--action", "rebuild",
    ])
    assert args_graph.command == "graph"
    assert args_graph.session_id == "sess_001"
    assert args_graph.action == "rebuild"


@pytest.mark.asyncio
async def test_container_initialize_database():
    """Kiểm tra container khởi tạo schema database thành công."""
    container = bootstrap_container()
    await container.initialize()
