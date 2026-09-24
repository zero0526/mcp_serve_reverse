import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.persistence.sqlite.connection import Base
from app.adapters.persistence.sqlite.session_log_repository import SQLiteSessionLogRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.application.task.create_task import CreateTaskUseCase
from app.application.task.get_evolution_report import GetToolEvolutionReportUseCase
from app.application.task.get_task import GetTaskUseCase
from app.application.task.list_tasks import ListTasksUseCase
from app.application.task.record_retrospective import RecordTaskRetrospectiveUseCase
from app.application.task.update_task import UpdateTaskUseCase
from app.domain.task.entities import TaskStatus
from app.interfaces.mcp.tools.task import (
    get_task_tool,
    get_tool_evolution_report_tool,
    list_tasks_tool,
    record_task_retrospective_tool,
    update_task_status_tool,
)


@pytest_asyncio.fixture
async def test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_task_with_multiple_urls(test_session_factory):
    task_repo = SQLiteTaskRepository(session_factory=test_session_factory)
    sess_repo = SQLiteSessionRepository(session_factory=test_session_factory)
    create_uc = CreateTaskUseCase(task_repository=task_repo, session_repository=sess_repo)
    get_uc = GetTaskUseCase(task_repository=task_repo)

    initial_urls = [
        "https://example.com/login",
        "https://example.com/checkout",
        "https://example.com/order",
    ]

    task = await create_uc.execute(
        task_id="task_001",
        name="Reverse Checkout Flow",
        goal_description="Crack the X-Signature header and replay order request",
        instructions="Step 1: Check storage for token. Step 2: Trace crypto hash.",
        env_vars={"API_KEY": "secret_123", "BASE_URL": "https://example.com"},
        initial_urls=initial_urls,
        browser_config={"headless": True, "use_cloakbrowser": False},
    )

    assert task.id == "task_001"
    assert task.name == "Reverse Checkout Flow"
    assert task.status == TaskStatus.CREATED
    assert len(task.initial_urls) == 3
    assert len(task.session_ids) == 3
    assert task.env_vars["API_KEY"] == "secret_123"

    # Verify each pre-created session exists in SessionRepository
    for sid in task.session_ids:
        sess = await sess_repo.get_by_id(sid)
        assert sess is not None
        assert sess["task_id"] == "task_001"

    # Fetch task via GetTaskUseCase
    fetched = await get_uc.execute("task_001")
    assert fetched is not None
    assert fetched.id == "task_001"
    assert len(fetched.session_ids) == 3


@pytest.mark.asyncio
async def test_list_and_update_task_status(test_session_factory):
    task_repo = SQLiteTaskRepository(session_factory=test_session_factory)
    create_uc = CreateTaskUseCase(task_repository=task_repo, session_factory=test_session_factory)
    list_uc = ListTasksUseCase(task_repository=task_repo)
    update_uc = UpdateTaskUseCase(task_repository=task_repo)

    await create_uc.execute(task_id="task_A", name="Task Alpha")
    await create_uc.execute(task_id="task_B", name="Task Beta")

    all_tasks = await list_uc.execute()
    assert len(all_tasks) == 2

    # Update Task Alpha to IN_PROGRESS
    ok = await update_uc.execute(task_id="task_A", status=TaskStatus.IN_PROGRESS, metadata_update={"notes": "Started"})
    assert ok is True

    in_progress_tasks = await list_uc.execute(status=TaskStatus.IN_PROGRESS)
    assert len(in_progress_tasks) == 1
    assert in_progress_tasks[0].id == "task_A"
    assert in_progress_tasks[0].metadata.get("notes") == "Started"


@pytest.mark.asyncio
async def test_record_retrospective_and_evolution_report(test_session_factory):
    task_repo = SQLiteTaskRepository(session_factory=test_session_factory)
    await task_repo.create(task_id="task_001", name="Task 001")
    await task_repo.create(task_id="task_002", name="Task 002")

    log_repo = SQLiteSessionLogRepository(session_factory=test_session_factory)
    record_uc = RecordTaskRetrospectiveUseCase(session_log_repository=log_repo)
    evolution_uc = GetToolEvolutionReportUseCase(session_log_repository=log_repo)

    # 1. Record retro 1 for task_001
    log1 = await record_uc.execute(
        task_id="task_001",
        agent_evaluation="Successfully identified crypto signature via WebCrypto hook, but struggled with Protobuf body decoding.",
        missing_tools=["decode_protobuf_stream", "unpack_obfuscated_js"],
        suggested_tools=[
            {
                "name": "decode_protobuf_stream",
                "purpose": "Automatically decode binary Protobuf payloads into JSON structure",
                "parameters": {"hex_or_base64_data": "string", "proto_hint": "optional string"},
            }
        ],
        bottlenecks=["Took 3 steps to manually extract raw bytes from NetworkResponse"],
        efficiency_rating=4,
    )
    assert log1.task_id == "task_001"
    assert "decode_protobuf_stream" in log1.missing_tools

    # 2. Record retro 2 for task_002
    await record_uc.execute(
        task_id="task_002",
        agent_evaluation="Lineage was clear, needed protobuf decoding as well.",
        missing_tools=["decode_protobuf_stream", "graphql_introspect"],
        suggested_tools=[],
        bottlenecks=["Manual decoding"],
        efficiency_rating=3,
    )

    # 3. Get overall evolution summary
    summary = await evolution_uc.execute()
    assert summary["total_retrospectives"] == 2
    assert summary["average_efficiency_rating"] == 3.5

    # decode_protobuf_stream was requested by both retrospectives -> frequency = 2
    top_tools = {item["tool"]: item["frequency"] for item in summary["top_missing_tools"]}
    assert top_tools["decode_protobuf_stream"] == 2
    assert top_tools["unpack_obfuscated_js"] == 1
    assert top_tools["graphql_introspect"] == 1
    assert len(summary["recent_proposals"]) == 1


@pytest.mark.asyncio
async def test_mcp_tools_task_layer():
    # Test task tools with default repositories
    # Create task via usecase to test tool querying
    import uuid
    tid = f"task_mcp_{uuid.uuid4().hex[:6]}"
    from app.application.task.create_task import CreateTaskUseCase
    create_uc = CreateTaskUseCase()
    await create_uc.execute(
        task_id=tid,
        name="MCP Integration Task",
        goal_description="Verify MCP task endpoints",
        instructions="Run tests",
        initial_urls=["https://test.local/api"],
    )

    # 1. get_task
    task_res = await get_task_tool(task_id=tid)
    assert task_res["status"] == "COMPLETED"
    assert task_res["data"]["id"] == tid
    assert len(task_res["data"]["session_ids"]) == 1

    # 2. list_tasks
    list_res = await list_tasks_tool(limit=10)
    assert list_res["status"] == "COMPLETED"
    assert any(t["id"] == tid for t in list_res["data"]["tasks"])

    # 3. update_task_status
    upd_res = await update_task_status_tool(task_id=tid, status="IN_PROGRESS")
    assert upd_res["status"] == "COMPLETED"
    assert upd_res["data"]["success"] is True

    # 4. record_task_retrospective
    retro_res = await record_task_retrospective_tool(
        task_id=tid,
        agent_evaluation="Good test run",
        missing_tools=["auto_curl_converter"],
        efficiency_rating=5,
    )
    assert retro_res["status"] == "COMPLETED"
    assert "log_id" in retro_res["data"]

    # 5. get_tool_evolution_report
    evo_res = await get_tool_evolution_report_tool(task_id=tid)
    assert evo_res["status"] == "COMPLETED"
    assert evo_res["data"]["total_retrospectives"] >= 1
