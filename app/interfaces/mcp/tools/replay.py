from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.generate_replay_spec import GenerateReplaySpecUseCase
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.application.replay.execute_replay import ExecuteReplayUseCase
from app.application.replay.prepare_replay import PrepareReplayUseCase
from app.application.replay.synthesize_code import SynthesizeCodeUseCase
from app.domain.replay.entities import ReplayMode
from app.interfaces.mcp.schemas.responses import create_mcp_response


def _get_use_cases():
    session_factory = AsyncSessionLocal
    graph_repo = SQLiteGraphRepository(session_factory=session_factory)
    diff_use_case = DifferentialAnalysisUseCase(session_factory=session_factory)
    trace_use_case = TraceLineageUseCase(graph_repo)
    generate_spec_use_case = GenerateReplaySpecUseCase(
        graph_repository=graph_repo,
        diff_use_case=diff_use_case,
        trace_use_case=trace_use_case,
        session_factory=session_factory,
    )
    prepare_use_case = PrepareReplayUseCase()
    execute_use_case = ExecuteReplayUseCase(
        prepare_use_case=prepare_use_case,
        session_factory=session_factory,
    )
    synthesize_use_case = SynthesizeCodeUseCase(
        generate_spec_use_case=generate_spec_use_case,
    )
    return generate_spec_use_case, prepare_use_case, execute_use_case, synthesize_use_case


async def prepare_replay_tool(
    task_id: str,
    target_request_id: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MCP Tool: Chuẩn bị request replay từ ReplaySpec."""
    gen_spec, prep, _, _ = _get_use_cases()
    spec = await gen_spec.execute(task_id, target_request_id)
    req = prep.execute(spec, variables=variables)
    data = {
        "status": "prepared",
        "task_id": task_id,
        "target_request_id": target_request_id,
        "request": req.model_dump(),
        "required_variables": spec.required_variables,
    }
    resp = create_mcp_response(
        status="COMPLETED",
        data=data,
        source="replay_engine",
    )
    resp.update(data)
    return resp


async def execute_replay_tool(
    task_id: str,
    target_request_id: str,
    variables: dict[str, Any] | None = None,
    mode: str = "dry_run",
    session_id: str | None = None,
    auto_resolve_dependencies: bool = False,
    allowed_hosts: list[str] | None = None,
    allow_mutation: bool = True,
) -> dict[str, Any]:
    """MCP Tool: Thực thi replay (hỗ trợ dry_run hoặc execute thực tế)."""
    from app.domain.replay.policies import ReplaySafetyPolicy

    replay_mode = ReplayMode(mode.lower().strip())
    gen_spec, _, exec_uc, _ = _get_use_cases()
    spec = await gen_spec.execute(task_id, target_request_id)

    policy = None
    if allowed_hosts is not None:
        policy = ReplaySafetyPolicy(
            allowed_hosts=allowed_hosts,
            allow_mutation=allow_mutation,
        )

    req, result, comparison = await exec_uc.execute(
        spec=spec,
        variables=variables,
        mode=replay_mode,
        policy=policy,
        session_id=session_id or task_id,
        auto_resolve_dependencies=auto_resolve_dependencies,
    )
    data = {
        "mode": str(replay_mode),
        "request": req.model_dump(),
        "execution_result": result.model_dump() if result else None,
        "comparison": comparison.model_dump() if comparison else None,
    }
    resp = create_mcp_response(
        status="COMPLETED",
        data=data,
        source="replay_engine",
    )
    resp.update(data)
    return resp


async def validate_replay_tool(
    task_id: str,
    target_request_id: str,
    variables: dict[str, Any] | None = None,
    allowed_hosts: list[str] | None = None,
    allowed_methods: list[str] | None = None,
    allow_mutation: bool = True,
) -> dict[str, Any]:
    """MCP Tool: Kiểm tra chính sách an toàn Replay trước khi phát lại request mạng."""
    from app.application.replay.validate_replay import ValidateReplayUseCase
    from app.domain.replay.policies import ReplaySafetyPolicy

    gen_spec, prep, _, _ = _get_use_cases()
    spec = await gen_spec.execute(task_id, target_request_id)
    req = prep.execute(spec, variables=variables)

    validator = ValidateReplayUseCase()
    policy = ReplaySafetyPolicy(
        allowed_hosts=allowed_hosts or [],
        allowed_methods=allowed_methods or ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        allow_mutation=allow_mutation,
    )
    res = validator.execute(req, policy)
    resp = create_mcp_response(
        status="COMPLETED",
        data=res,
        source="replay_safety",
    )
    resp.update(res)
    return resp


async def resolve_dependencies_tool(
    session_id: str,
    target_request_id: str,
    variables: dict[str, Any] | None = None,
    auto_execute_prerequisites: bool = False,
) -> dict[str, Any]:
    """MCP Tool: Phân tích và tự động giải quyết các request phụ thuộc tuần tự (ví dụ: login lấy token)."""
    from app.application.replay.resolve_dependencies import ResolveDependenciesUseCase

    resolver = ResolveDependenciesUseCase(session_factory=AsyncSessionLocal)
    plan = await resolver.execute(
        session_id=session_id,
        target_request_id=target_request_id,
        variables=variables,
        auto_execute_prerequisites=auto_execute_prerequisites,
    )
    resp = create_mcp_response(
        status="COMPLETED",
        data=plan,
        source="replay_dependency_resolver",
    )
    resp.update(plan)
    return resp


async def synthesize_code_tool(
    task_id: str,
    target_request_id: str,
    language: str = "python",
) -> dict[str, Any]:
    """MCP Tool: Tự động sinh mã nguồn (Python, cURL, TypeScript) từ ReplaySpec."""
    _, _, _, synth_uc = _get_use_cases()
    res = await synth_uc.execute(
        task_id=task_id,
        target_request_id=target_request_id,
        language=language,
    )
    data = res.model_dump()
    resp = create_mcp_response(
        status="COMPLETED",
        data=data,
        source="code_synthesis",
    )
    resp.update(data)
    return resp
