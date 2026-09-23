"""MCP Server implementation for api_lineage.

Exposes Model Context Protocol tools for reverse-engineering web applications,
capturing runtime events, analyzing call stacks & data lineages, and synthesizing replay code.
"""

from typing import Any
from mcp.server.mcpserver import MCPServer

from app.interfaces.mcp.resources import (
    get_lineage_resource,
    get_request_resource,
    get_session_resource,
)
from app.interfaces.mcp.tools.capture import (
    get_capture_status_tool,
    start_capture_session_tool,
    stop_capture_session_tool,
)
from app.interfaces.mcp.tools.graph import (
    get_graph_neighbors_tool,
    get_graph_node_tool,
    get_graph_statistics_tool,
)
from app.interfaces.mcp.tools.lineage import (
    compare_lineage_tool,
    explain_lineage_path_tool,
    find_transformations_tool,
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
    execute_replay_tool,
    prepare_replay_tool,
    resolve_dependencies_tool,
    synthesize_code_tool,
    validate_replay_tool,
)
from app.interfaces.mcp.tools.trace import (
    get_execution_context_tool,
    get_trace_timeline_tool,
    search_trace_events_tool,
)


def create_mcp_server() -> MCPServer:
    """Tạo và đăng ký toàn bộ MCP Tools cho api_lineage."""
    server = MCPServer("api_lineage")

    # 1. Capture Tools
    @server.tool()
    async def start_capture_session(
        name: str,
        target: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Khởi tạo phiên capture thu thập dữ liệu trình duyệt."""
        return await start_capture_session_tool(
            name=name, target=target, task_id=task_id, session_id=session_id, options=options
        )

    @server.tool()
    async def stop_capture_session(session_id: str) -> dict[str, Any]:
        """Dừng phiên capture và đóng tài nguyên trình duyệt."""
        return await stop_capture_session_tool(session_id=session_id)

    @server.tool()
    async def get_capture_status(session_id: str) -> dict[str, Any]:
        """Xem trạng thái và thống kê sự kiện của phiên capture."""
        return await get_capture_status_tool(session_id=session_id)

    # 2. Trace Tools
    @server.tool()
    async def search_trace_events(
        session_id: str,
        event_types: list[str] | None = None,
        page_id: str | None = None,
        start_ns: int | None = None,
        end_ns: int | None = None,
        keyword: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Tìm kiếm các sự kiện vết gốc (Trace Events) có bộ lọc và phân trang."""
        return await search_trace_events_tool(
            session_id=session_id,
            event_types=event_types,
            page_id=page_id,
            start_ns=start_ns,
            end_ns=end_ns,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    @server.tool()
    async def get_trace_timeline(
        session_id: str,
        event_types: list[str] | None = None,
        start_ns: int | None = None,
        end_ns: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Lấy dòng thời gian sự kiện theo thứ tự diễn ra."""
        return await get_trace_timeline_tool(
            session_id=session_id,
            event_types=event_types,
            start_ns=start_ns,
            end_ns=end_ns,
            limit=limit,
        )

    @server.tool()
    async def get_execution_context(
        session_id: str,
        execution_id: str,
        include_arguments: bool = True,
        include_return_value: bool = True,
        include_stack_trace: bool = True,
        include_related_network: bool = True,
        include_call_tree: bool = True,
        max_related_events: int = 30,
    ) -> dict[str, Any]:
        """Lấy toàn bộ context thực thi hàm (caller/callee tree, args, return value, stack, network)."""
        return await get_execution_context_tool(
            session_id=session_id,
            execution_id=execution_id,
            include_arguments=include_arguments,
            include_return_value=include_return_value,
            include_stack_trace=include_stack_trace,
            include_related_network=include_related_network,
            include_call_tree=include_call_tree,
            max_related_events=max_related_events,
        )

    # 3. Graph Query Tools
    @server.tool()
    async def get_graph_node(
        session_id: str,
        node_id: str,
        include_evidence: bool = True,
    ) -> dict[str, Any]:
        """Lấy thông tin chi tiết một GraphNode và evidence kết nối."""
        return await get_graph_node_tool(
            session_id=session_id, node_id=node_id, include_evidence=include_evidence
        )

    @server.tool()
    async def get_graph_neighbors(
        session_id: str,
        node_id: str,
        direction: str = "both",
        edge_types: list[str] | None = None,
        min_confidence: float = 0.8,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Lấy danh sách các node lân cận 1-hop (in/out/both)."""
        return await get_graph_neighbors_tool(
            session_id=session_id,
            node_id=node_id,
            direction=direction,
            edge_types=edge_types,
            min_confidence=min_confidence,
            limit=limit,
        )

    @server.tool()
    async def get_graph_statistics(
        session_id: str,
        include_edge_distribution: bool = True,
        include_orphans: bool = True,
    ) -> dict[str, Any]:
        """Lấy số liệu thống kê chất lượng đồ thị và phân bố quan hệ."""
        return await get_graph_statistics_tool(
            session_id=session_id,
            include_edge_distribution=include_edge_distribution,
            include_orphans=include_orphans,
        )

    # 4. Lineage Analysis Tools
    @server.tool()
    async def trace_origin(
        session_id: str,
        target_node_id: str,
        max_depth: int = 10,
        max_paths: int = 20,
        min_confidence: float = 0.8,
        include_heuristics: bool = False,
    ) -> dict[str, Any]:
        """Truy vết ngược tìm nguồn gốc dữ liệu của một node hoặc tham số."""
        return await trace_origin_tool(
            session_id=session_id,
            target_node_id=target_node_id,
            max_depth=max_depth,
            max_paths=max_paths,
            min_confidence=min_confidence,
            include_heuristics=include_heuristics,
        )

    @server.tool()
    async def trace_downstream(
        session_id: str,
        source_node_id: str,
        max_depth: int = 10,
        max_nodes: int = 200,
        min_confidence: float = 0.8,
    ) -> dict[str, Any]:
        """Tìm nơi dữ liệu được sử dụng xuôi dòng trong workflow."""
        return await trace_downstream_tool(
            session_id=session_id,
            source_node_id=source_node_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            min_confidence=min_confidence,
        )

    @server.tool()
    async def explain_lineage_path(
        session_id: str,
        target_node_id: str,
        path_id: str | None = None,
    ) -> dict[str, Any]:
        """Diễn giải chuỗi chứng minh lineage thành văn bản dễ hiểu kèm bằng chứng."""
        return await explain_lineage_path_tool(
            session_id=session_id, target_node_id=target_node_id, path_id=path_id
        )

    @server.tool()
    async def compare_lineage(
        left_session_id: str,
        left_node_id: str,
        right_session_id: str,
        right_node_id: str,
        comparison_mode: str = "structure",
    ) -> dict[str, Any]:
        """So sánh hai đường dẫn lineage hoặc so sánh giữa hai session."""
        return await compare_lineage_tool(
            left_session_id=left_session_id,
            left_node_id=left_node_id,
            right_session_id=right_session_id,
            right_node_id=right_node_id,
            comparison_mode=comparison_mode,
        )

    @server.tool()
    async def find_transformations(
        session_id: str,
        source: dict[str, Any] | str | None = None,
        target: dict[str, Any] | str | None = None,
        transformation_types: list[str] | None = None,
        direction: str = "both",
        max_depth: int = 10,
        include_arguments: bool = True,
    ) -> dict[str, Any]:
        """Phân tích chuỗi các hàm biến đổi dữ liệu liên tiếp (encode, hash, encrypt, serialize)."""
        return await find_transformations_tool(
            session_id=session_id,
            source=source,
            target=target,
            transformation_types=transformation_types,
            direction=direction,
            max_depth=max_depth,
            include_arguments=include_arguments,
        )

    # 5. Network Analysis Tools
    @server.tool()
    async def summarize_request(
        session_id: str,
        request_id: str,
        include_headers: bool = True,
        include_response: bool = True,
        redaction_mode: str = "strict",
    ) -> dict[str, Any]:
        """Tóm tắt chi tiết HTTP Request/Response kèm cơ chế che giấu dữ liệu nhạy cảm."""
        return await summarize_request_tool(
            session_id=session_id,
            request_id=request_id,
            include_headers=include_headers,
            include_response=include_response,
            redaction_mode=redaction_mode,
        )

    @server.tool()
    async def analyze_request_lineage(
        session_id: str,
        request_id: str,
        min_confidence: float = 0.8,
    ) -> dict[str, Any]:
        """Phân tích toàn diện nguồn gốc các tham số cấu thành một HTTP Request."""
        return await analyze_request_lineage_tool(
            session_id=session_id,
            request_id=request_id,
            min_confidence=min_confidence,
        )

    @server.tool()
    async def find_request_dependencies(
        session_id: str,
        request_id: str,
        include_storage: bool = True,
        include_executions: bool = True,
        max_depth: int = 10,
    ) -> dict[str, Any]:
        """Tìm các phụ thuộc (storage, execution, value) của một request."""
        return await find_request_dependencies_tool(
            session_id=session_id,
            request_id=request_id,
            include_storage=include_storage,
            include_executions=include_executions,
            max_depth=max_depth,
        )

    @server.tool()
    async def compare_requests(
        left_session_id: str,
        left_request_id: str,
        right_session_id: str,
        right_request_id: str,
        redaction_mode: str = "strict",
    ) -> dict[str, Any]:
        """So sánh hai HTTP Request để tìm ra sự khác biệt."""
        return await compare_requests_tool(
            left_session_id=left_session_id,
            left_request_id=left_request_id,
            right_session_id=right_session_id,
            right_request_id=right_request_id,
            redaction_mode=redaction_mode,
        )

    # 6. Replay Engine Tools
    @server.tool()
    async def prepare_replay(
        task_id: str,
        target_request_id: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Chuẩn bị request replay từ ReplaySpec."""
        return await prepare_replay_tool(
            task_id=task_id, target_request_id=target_request_id, variables=variables
        )

    @server.tool()
    async def execute_replay(
        task_id: str,
        target_request_id: str,
        variables: dict[str, Any] | None = None,
        mode: str = "dry_run",
        session_id: str | None = None,
        auto_resolve_dependencies: bool = False,
        allowed_hosts: list[str] | None = None,
        allow_mutation: bool = True,
    ) -> dict[str, Any]:
        """Thực thi request replay (hỗ trợ dry_run hoặc execute thực tế, tự động resolve dependencies và validate safety)."""
        return await execute_replay_tool(
            task_id=task_id,
            target_request_id=target_request_id,
            variables=variables,
            mode=mode,
            session_id=session_id,
            auto_resolve_dependencies=auto_resolve_dependencies,
            allowed_hosts=allowed_hosts,
            allow_mutation=allow_mutation,
        )

    @server.tool()
    async def validate_replay(
        task_id: str,
        target_request_id: str,
        variables: dict[str, Any] | None = None,
        allowed_hosts: list[str] | None = None,
        allowed_methods: list[str] | None = None,
        allow_mutation: bool = True,
    ) -> dict[str, Any]:
        """Kiểm tra chính sách an toàn Replay trước khi phát lại (whitelist host, method, unreplaced secret placeholders)."""
        return await validate_replay_tool(
            task_id=task_id,
            target_request_id=target_request_id,
            variables=variables,
            allowed_hosts=allowed_hosts,
            allowed_methods=allowed_methods,
            allow_mutation=allow_mutation,
        )

    @server.tool()
    async def resolve_dependencies(
        session_id: str,
        target_request_id: str,
        variables: dict[str, Any] | None = None,
        auto_execute_prerequisites: bool = False,
    ) -> dict[str, Any]:
        """Tự động phân tích và giải quyết các request phụ thuộc tuần tự (ví dụ: login lấy token nạp vào request sau)."""
        return await resolve_dependencies_tool(
            session_id=session_id,
            target_request_id=target_request_id,
            variables=variables,
            auto_execute_prerequisites=auto_execute_prerequisites,
        )

    @server.tool()
    async def synthesize_code(
        task_id: str,
        target_request_id: str,
        language: str = "python",
    ) -> dict[str, Any]:
        """Tự động sinh mã nguồn (Python, cURL, TypeScript) tái hiện request."""
        return await synthesize_code_tool(
            task_id=task_id, target_request_id=target_request_id, language=language
        )

    # 7. MCP Resources
    @server.resource(
        "session://{session_id}",
        name="session_resource",
        description="Metadata và tóm tắt tổng quan một phiên capture (session).",
        mime_type="application/json",
    )
    async def session_resource(session_id: str) -> str:
        """Đọc metadata và tóm tắt session theo chuẩn MCP."""
        return await get_session_resource(session_id=session_id)

    @server.resource(
        "request://{session_id}/{request_id}",
        name="request_resource",
        description="Chi tiết HTTP request, response và lineage tóm tắt.",
        mime_type="application/json",
    )
    async def request_resource(session_id: str, request_id: str) -> str:
        """Đọc chi tiết request, response và lineage tóm tắt theo chuẩn MCP."""
        return await get_request_resource(session_id=session_id, request_id=request_id)

    @server.resource(
        "lineage://{session_id}/{node_id}",
        name="lineage_resource",
        description="Cây nguồn gốc và tác động xuôi dòng của một node/giá trị.",
        mime_type="application/json",
    )
    async def lineage_resource(session_id: str, node_id: str) -> str:
        """Đọc cây nguồn gốc và tác động xuôi dòng theo chuẩn MCP."""
        return await get_lineage_resource(session_id=session_id, node_id=node_id)

    return server


server = create_mcp_server()


def main():
    """Điểm khởi chạy MCP Server qua standard I/O."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
