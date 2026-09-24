"""MCP Prompts definition for api_lineage.

Provides standard workflow templates exposed via the Model Context Protocol prompts capability.
Clients like Claude Desktop, Cursor, or Antigravity can display these prompts in their slash command
or prompt selection menus.
"""

from mcp.server.mcpserver import MCPServer


def register_mcp_prompts(server: MCPServer) -> None:
    """Đăng ký các mẫu Prompt chuẩn cho server MCP api_lineage."""

    @server.prompt(
        name="reverse_api_workflow",
        description="Quy trình chuẩn A-Z để phân tích và bóc tách một API endpoint từ Task ID được giao.",
    )
    def reverse_api_workflow(task_id: str, endpoint_filter: str = "") -> str:
        filter_clause = f" Lọc theo endpoint/từ khóa: '{endpoint_filter}'." if endpoint_filter else ""
        return (
            f"Bạn được giao thực hiện nhiệm vụ dịch ngược API cho Task '{task_id}'.{filter_clause}\n\n"
            "Hãy thực hiện nghiêm ngặt theo quy trình 5 bước sau:\n"
            "1. Gọi `get_task(task_id='{task_id}')` để đọc mục tiêu, biến môi trường và danh sách session con.\n"
            "2. Gọi `list_requests(session_id=...)` để xác định chính xác HTTP Request mục tiêu cần đảo ngược.\n"
            "3. Gọi `summarize_request` và `compact_graph` để làm sạch Property Graph, kiểm tra schema request.\n"
            "4. Sử dụng `trace_origin` và `find_transformations` để truy vết nguồn gốc các tham số mã hóa/chữ ký.\n"
            "   (Nếu có nhiều session cùng task_id, hãy gọi `differential_analysis(task_id='{task_id}')`).\n"
            "5. Kiểm tra tính tái hiện bằng `execute_replay` hoặc sinh mã tái hiện bằng `synthesize_code`.\n"
            "6. BẮT BUỘC: Trước khi kết thúc, gọi `record_task_retrospective` để nhận xét hiệu quả các tool MCP,\n"
            "   chỉ ra các tool còn thiếu, sau đó gọi `update_task_status(task_id='{task_id}', status='COMPLETED')."
        )

    @server.prompt(
        name="signature_analysis_workflow",
        description="Quy trình chuyên sâu bóc tách chữ ký bảo mật, token xác thực (HMAC, SHA-256, Web Crypto, Nonce).",
    )
    def signature_analysis_workflow(session_id: str, signature_name: str) -> str:
        return (
            f"Hãy phân tích và truy vết thuật toán tạo ra chữ ký/tham số '{signature_name}' trong phiên '{session_id}':\n\n"
            f"1. Xác định node ID của tham số '{signature_name}' trong request liên quan.\n"
            f"2. Gọi `trace_origin(session_id='{session_id}', target_node_id=...)` để lần ngược dữ liệu.\n"
            f"3. Gọi `find_transformations(session_id='{session_id}', ...)` để kiểm tra các hàm mã hóa/băm (crypto_operation, serialize).\n"
            f"4. Gọi `explain_lineage_path` để xuất chuỗi giải thích nguồn gốc có bằng chứng (evidence).\n"
            "5. Đưa ra công thức hoặc mã giả (pseudocode) tái tạo lại chính xác chữ ký này."
        )

    @server.prompt(
        name="evolution_retrospective_workflow",
        description="Mẫu hướng dẫn Agent tự đánh giá bộ công cụ MCP sau khi hoàn thành task để đóng góp vào tiến hóa hệ thống.",
    )
    def evolution_retrospective_workflow(task_id: str) -> str:
        return (
            f"Tiến hành đánh giá hồi cứu (Task Retrospective) cho Task '{task_id}':\n\n"
            "1. Rà soát lại toàn bộ các công cụ MCP bạn đã gọi trong suốt quá trình xử lý task.\n"
            "2. Xác định các điểm nghẽn (bottlenecks): tool nào chạy chậm, tool nào trả về quá nhiều dữ liệu rác, hoặc phải gọi vòng vèo.\n"
            "3. Liệt kê các công cụ còn thiếu (missing tools) mà nếu có sẵn sẽ giúp bạn giải quyết bài toán nhanh hơn ít nhất 50%.\n"
            "4. Đề xuất thông số chi tiết (tên tool, input schema, output mong muốn) cho các công cụ mới.\n"
            f"5. Gọi `record_task_retrospective(task_id='{task_id}', ...)` với đánh giá trung thực từ 1 đến 5 sao."
        )
