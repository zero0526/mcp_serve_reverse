"""Composition Root (Dependency Injection Container) for api_lineage.

Initializes database infrastructure, repositories, adapters, use cases,
and MCP server wiring in a single unified container.
"""

from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.adapters.graph.graph_projector import GraphProjector
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal, init_db
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.adapters.replay.http_client import HttpxReplayExecutor

# Phase 1 Use Cases
from app.application.capture.capture_status import CaptureStatusUseCase
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.application.ingest.normalize_event import EventNormalizer, event_normalizer
from app.application.ingest.validate_event import EventValidator, event_validator

# Phase 2 Use Cases
from app.application.graph.compact_graph import CompactGraphUseCase
from app.application.graph.project_event import ProjectEventUseCase
from app.application.graph.rebuild_graph import RebuildGraphUseCase
from app.application.lineage.compare_lineage import CompareLineageUseCase
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.explain_path import ExplainLineagePathUseCase
from app.application.lineage.find_transformations import FindTransformationsUseCase
from app.application.lineage.generate_replay_spec import GenerateReplaySpecUseCase
from app.application.lineage.trace_downstream import TraceDownstreamUseCase
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.application.lineage.trace_origin import TraceOriginUseCase

# Phase 3 Use Cases
from app.application.network.analyze_request_lineage import AnalyzeRequestLineageUseCase
from app.application.network.compare_requests import CompareRequestsUseCase
from app.application.network.find_request_dependencies import FindRequestDependenciesUseCase
from app.application.network.summarize_request import SummarizeRequestUseCase
from app.application.trace.get_execution_context import GetExecutionContextUseCase
from app.application.trace.get_timeline import GetTraceTimelineUseCase
from app.application.trace.search_events import SearchTraceEventsUseCase

# Phase 5 Use Cases
from app.application.replay.compare_responses import CompareResponsesUseCase
from app.application.replay.execute_replay import ExecuteReplayUseCase
from app.application.replay.prepare_replay import PrepareReplayUseCase
from app.application.replay.resolve_dependencies import ResolveDependenciesUseCase
from app.application.replay.synthesize_code import SynthesizeCodeUseCase
from app.application.replay.validate_replay import ValidateReplayUseCase

from app.adapters.persistence.sqlite.session_log_repository import SQLiteSessionLogRepository
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository

# Task & Evolution Use Cases
from app.application.task.create_task import CreateTaskUseCase
from app.application.task.get_evolution_report import GetToolEvolutionReportUseCase
from app.application.task.get_task import GetTaskUseCase
from app.application.task.list_tasks import ListTasksUseCase
from app.application.task.record_retrospective import RecordTaskRetrospectiveUseCase
from app.application.task.update_task import UpdateTaskUseCase

from app.infrastructure.serialization.redaction import RedactionEngine, redaction_engine
from app.interfaces.mcp.context import TruncationGuard, default_truncation_guard
from app.interfaces.mcp.server import create_mcp_server


@dataclass
class ApplicationContainer:
    """Dependency Injection Container chứa toàn bộ hạ tầng và nghiệp vụ của hệ thống."""

    # Persistence & Repositories
    session_factory: Any
    session_repository: SQLiteSessionRepository
    event_repository: SQLiteEventRepository
    graph_repository: SQLiteGraphRepository
    task_repository: SQLiteTaskRepository
    session_log_repository: SQLiteSessionLogRepository

    # Adapters & Services
    http_executor: HttpxReplayExecutor
    redaction_engine: RedactionEngine
    event_validator: EventValidator
    event_normalizer: EventNormalizer
    graph_projector: GraphProjector
    truncation_guard: TruncationGuard

    # Task Management & MCP Evolution
    create_task_uc: CreateTaskUseCase
    get_task_uc: GetTaskUseCase
    list_tasks_uc: ListTasksUseCase
    update_task_uc: UpdateTaskUseCase
    record_retrospective_uc: RecordTaskRetrospectiveUseCase
    get_evolution_report_uc: GetToolEvolutionReportUseCase

    # Phase 1: Capture & Ingest
    start_session_uc: StartSessionUseCase
    stop_session_uc: StopSessionUseCase
    capture_status_uc: CaptureStatusUseCase
    ingest_event_uc: IngestEventUseCase

    # Phase 2: Graph Lifecycle & Lineage
    project_event_uc: ProjectEventUseCase
    rebuild_graph_uc: RebuildGraphUseCase
    compact_graph_uc: CompactGraphUseCase
    trace_origin_uc: TraceOriginUseCase
    trace_downstream_uc: TraceDownstreamUseCase
    trace_lineage_uc: TraceLineageUseCase
    explain_lineage_uc: ExplainLineagePathUseCase
    compare_lineage_uc: CompareLineageUseCase
    find_transformations_uc: FindTransformationsUseCase
    differential_analysis_uc: DifferentialAnalysisUseCase

    # Phase 3: Trace & Network Context
    get_execution_context_uc: GetExecutionContextUseCase
    search_trace_events_uc: SearchTraceEventsUseCase
    get_trace_timeline_uc: GetTraceTimelineUseCase
    summarize_request_uc: SummarizeRequestUseCase
    compare_requests_uc: CompareRequestsUseCase
    find_request_dependencies_uc: FindRequestDependenciesUseCase
    analyze_request_lineage_uc: AnalyzeRequestLineageUseCase

    # Phase 5: Replay & Code Synthesis
    prepare_replay_uc: PrepareReplayUseCase
    validate_replay_uc: ValidateReplayUseCase
    resolve_dependencies_uc: ResolveDependenciesUseCase
    generate_replay_spec_uc: GenerateReplaySpecUseCase
    compare_responses_uc: CompareResponsesUseCase
    execute_replay_uc: ExecuteReplayUseCase
    synthesize_code_uc: SynthesizeCodeUseCase

    # MCP Server
    mcp_server: MCPServer

    async def initialize(self) -> None:
        """Khởi tạo cấu trúc schema cơ sở dữ liệu SQLite."""
        await init_db()


def bootstrap_container(session_factory=AsyncSessionLocal) -> ApplicationContainer:
    """Khởi tạo và kết nối (wiring) tự động toàn bộ container hệ thống."""
    # 1. Repositories
    session_repo = SQLiteSessionRepository(session_factory=session_factory)
    event_repo = SQLiteEventRepository(session_factory=session_factory)
    graph_repo = SQLiteGraphRepository(session_factory=session_factory)
    task_repo = SQLiteTaskRepository(session_factory=session_factory)
    session_log_repo = SQLiteSessionLogRepository(session_factory=session_factory)

    # 1.1 Task & Evolution Use Cases
    create_task_uc = CreateTaskUseCase(
        task_repository=task_repo,
        session_repository=session_repo,
        session_factory=session_factory,
    )
    get_task_uc = GetTaskUseCase(task_repository=task_repo, session_factory=session_factory)
    list_tasks_uc = ListTasksUseCase(task_repository=task_repo, session_factory=session_factory)
    update_task_uc = UpdateTaskUseCase(task_repository=task_repo, session_factory=session_factory)
    record_retro_uc = RecordTaskRetrospectiveUseCase(
        session_log_repository=session_log_repo, session_factory=session_factory
    )
    get_evolution_uc = GetToolEvolutionReportUseCase(
        session_log_repository=session_log_repo, session_factory=session_factory
    )

    # 2. Adapters
    http_executor = HttpxReplayExecutor()
    redactor = redaction_engine
    validator = event_validator
    normalizer = event_normalizer
    projector = GraphProjector()
    trunc_guard = default_truncation_guard

    # 3. Phase 1 Use Cases
    active_browsers: dict[str, Any] = {}
    ingest_event_uc = IngestEventUseCase(
        event_store=event_repo,
        validator=validator,
        normalizer=normalizer,
        redactor=redactor,
    )
    start_session_uc = StartSessionUseCase(
        session_repository=session_repo,
        ingest_use_case=ingest_event_uc,
    )
    start_session_uc.active_browsers = active_browsers
    stop_session_uc = StopSessionUseCase(
        session_repository=session_repo,
        active_browsers=active_browsers,
    )
    capture_status_uc = CaptureStatusUseCase(session_repository=session_repo)

    # 4. Phase 2 Use Cases
    project_event_uc = ProjectEventUseCase(
        graph_repository=graph_repo,
        session_factory=session_factory,
    )
    rebuild_graph_uc = RebuildGraphUseCase(
        graph_repository=graph_repo,
        projector=projector,
        session_factory=session_factory,
    )
    compact_graph_uc = CompactGraphUseCase(
        graph_repository=graph_repo,
        session_factory=session_factory,
    )
    trace_lineage_uc = TraceLineageUseCase(graph_repository=graph_repo)
    trace_origin_uc = TraceOriginUseCase(graph_repo=graph_repo, session_factory=session_factory)
    trace_downstream_uc = TraceDownstreamUseCase(graph_repo=graph_repo, session_factory=session_factory)
    explain_lineage_uc = ExplainLineagePathUseCase(graph_repo=graph_repo, session_factory=session_factory)
    compare_lineage_uc = CompareLineageUseCase(graph_repo=graph_repo, session_factory=session_factory)
    find_transformations_uc = FindTransformationsUseCase(session_factory=session_factory)
    diff_analysis_uc = DifferentialAnalysisUseCase(session_factory=session_factory)

    # 5. Phase 3 Use Cases
    get_exec_ctx_uc = GetExecutionContextUseCase(session_factory=session_factory)
    search_events_uc = SearchTraceEventsUseCase(session_factory=session_factory)
    get_timeline_uc = GetTraceTimelineUseCase(session_factory=session_factory)
    summarize_req_uc = SummarizeRequestUseCase(session_factory=session_factory)
    compare_reqs_uc = CompareRequestsUseCase(session_factory=session_factory)
    find_req_deps_uc = FindRequestDependenciesUseCase(graph_repo=graph_repo, session_factory=session_factory)
    analyze_req_lineage_uc = AnalyzeRequestLineageUseCase(graph_repo=graph_repo, session_factory=session_factory)

    # 6. Phase 5 Use Cases
    prepare_replay_uc = PrepareReplayUseCase()
    validate_replay_uc = ValidateReplayUseCase()
    resolve_deps_uc = ResolveDependenciesUseCase(
        session_factory=session_factory,
        http_executor=http_executor,
    )
    generate_spec_uc = GenerateReplaySpecUseCase(
        graph_repository=graph_repo,
        diff_use_case=diff_analysis_uc,
        trace_use_case=trace_lineage_uc,
        session_factory=session_factory,
    )
    compare_resp_uc = CompareResponsesUseCase()
    execute_replay_uc = ExecuteReplayUseCase(
        http_executor=http_executor,
        prepare_use_case=prepare_replay_uc,
        compare_use_case=compare_resp_uc,
        validate_use_case=validate_replay_uc,
        resolve_dependencies_use_case=resolve_deps_uc,
        session_factory=session_factory,
    )
    synthesize_code_uc = SynthesizeCodeUseCase(
        generate_spec_use_case=generate_spec_uc,
    )

    # 7. MCP Server
    mcp_server = create_mcp_server()

    return ApplicationContainer(
        session_factory=session_factory,
        session_repository=session_repo,
        event_repository=event_repo,
        graph_repository=graph_repo,
        task_repository=task_repo,
        session_log_repository=session_log_repo,
        http_executor=http_executor,
        redaction_engine=redactor,
        event_validator=validator,
        event_normalizer=normalizer,
        graph_projector=projector,
        truncation_guard=trunc_guard,
        create_task_uc=create_task_uc,
        get_task_uc=get_task_uc,
        list_tasks_uc=list_tasks_uc,
        update_task_uc=update_task_uc,
        record_retrospective_uc=record_retro_uc,
        get_evolution_report_uc=get_evolution_uc,
        start_session_uc=start_session_uc,
        stop_session_uc=stop_session_uc,
        capture_status_uc=capture_status_uc,
        ingest_event_uc=ingest_event_uc,
        project_event_uc=project_event_uc,
        rebuild_graph_uc=rebuild_graph_uc,
        compact_graph_uc=compact_graph_uc,
        trace_origin_uc=trace_origin_uc,
        trace_downstream_uc=trace_downstream_uc,
        trace_lineage_uc=trace_lineage_uc,
        explain_lineage_uc=explain_lineage_uc,
        compare_lineage_uc=compare_lineage_uc,
        find_transformations_uc=find_transformations_uc,
        differential_analysis_uc=diff_analysis_uc,
        get_execution_context_uc=get_exec_ctx_uc,
        search_trace_events_uc=search_events_uc,
        get_trace_timeline_uc=get_timeline_uc,
        summarize_request_uc=summarize_req_uc,
        compare_requests_uc=compare_reqs_uc,
        find_request_dependencies_uc=find_req_deps_uc,
        analyze_request_lineage_uc=analyze_req_lineage_uc,
        prepare_replay_uc=prepare_replay_uc,
        validate_replay_uc=validate_replay_uc,
        resolve_dependencies_uc=resolve_deps_uc,
        generate_replay_spec_uc=generate_spec_uc,
        compare_responses_uc=compare_resp_uc,
        execute_replay_uc=execute_replay_uc,
        synthesize_code_uc=synthesize_code_uc,
        mcp_server=mcp_server,
    )
