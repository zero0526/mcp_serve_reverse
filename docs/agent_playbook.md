# Cẩm Nang Tác Vụ & Lựa Chọn MCP Tool Cho Agent (Agent Playbook)

> **Mục tiêu tài liệu**: Hướng dẫn chi tiết cách thức cấu hình, cơ chế nạp System Prompt, bản đồ định tuyến công cụ (Tool Routing Matrix) và quy trình chuẩn (SOP) để bất kỳ LLM Agent nào (như Claude, Cursor, Antigravity, Cline) khi kết nối vào server `api_lineage` đều có thể tự động chọn đúng tool, phân tích chính xác và không làm tràn Context Window.

---

## 1. Cơ Chế Nạp System Prompt & Hướng Dẫn Trong MCP

Trong kiến trúc Model Context Protocol (MCP), tài liệu và System Prompt hướng dẫn Agent được chia thành **4 cấp độ**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Cấp 1: Protocol Instructions (MCPServer instructions)                   │
│ Tự động gửi trong packet JSON-RPC "initialize" làm System Prompt ngầm   │
├────────────────────────────────────────────────────────────────────────┤
│ Cấp 2: MCP Prompts (@server.prompt())                                  │
│ Hiển thị trong menu "/" hoặc "slash commands" của IDE/Chat UI          │
├────────────────────────────────────────────────────────────────────────┤
│ Cấp 3: Tool Docstrings & Parameter Schemas                             │
│ LLM đọc mô tả chi tiết của từng tool khi quyết định gọi hàm            │
├────────────────────────────────────────────────────────────────────────┤
│ Cấp 4: Agent Playbook / Workspace Rules (docs/agent_playbook.md)       │
│ Tài liệu kiến thức toàn diện tra cứu cho cả kỹ sư và AI                │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Cấp 1 - Protocol-Level Instructions**:
   - Được định nghĩa tại [app/interfaces/mcp/instructions.py](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/instructions.py) và truyền vào `MCPServer(name="api_lineage", instructions=MCP_SERVER_INSTRUCTIONS)`.
   - Ngay khi Agent kết nối qua `stdio` hoặc `sse`, server trả về chuỗi instructions này. Client MCP (Claude Desktop, Cursor, Antigravity) sẽ **tự động chèn đoạn này vào đầu System Prompt** của phiên chat.
2. **Cấp 2 - MCP Prompts Template**:
   - Được định nghĩa tại [app/interfaces/mcp/prompts.py](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/prompts.py) và phơi ra qua endpoint `prompts/list`.
   - Cung cấp các kịch bản mẫu kích hoạt nhanh:
     - `reverse_api_workflow(task_id, endpoint_filter)`
     - `signature_analysis_workflow(session_id, signature_name)`
     - `evolution_retrospective_workflow(task_id)`
3. **Cấp 3 - Tool Descriptions**:
   - Khai báo tại từng hàm `@server.tool()` trong [app/interfaces/mcp/server.py](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/server.py).
4. **Cấp 4 - Playbook Tài liệu (File này)**:
   - Nằm tại [docs/agent_playbook.md](file:///d:/source_code/mcp_serve_reverse/docs/agent_playbook.md) phục vụ cả human developer đọc và nhúng vào config của các IDE.

---

## 2. Bản Đồ Định Tuyến Công Cụ (Tool Selection Decision Matrix)

Khi đứng trước một bài toán cụ thể, Agent cần tra cứu bảng sau để chọn công cụ tối ưu:

| Tình huống / Mục tiêu nghiệp vụ | Công cụ Ưu tiên (Nên Dùng) | Công cụ Phụ trợ | Hành vi CẦN TRÁNH |
| :--- | :--- | :--- | :--- |
| **Nhận một Task ID (vd: `task_001`)** | `get_task(task_id)` | `list_sessions(task_id=...)` | Không quét mò mẫm khi chưa đọc goal & hướng dẫn |
| **Tìm danh sách session đang có** | `list_sessions(task_id, limit)` | `get_capture_status` | Không đoán bừa session ID |
| **Khám phá các API endpoint trong session** | `list_requests(session_id, method="POST", url_keyword="...")` | `summarize_request` | Không gọi `search_trace_events` thô để quét URL |
| **Xem chi tiết headers/body một request** | `summarize_request(session_id, request_id)` | `find_request_dependencies` | Không tắt redaction mode |
| **Truy vết nguồn gốc tham số/token động** | `trace_origin(session_id, target_node_id)` | `explain_lineage_path` | Không đoán mò quy luật tạo token |
| **Bóc tách hàm băm/mã hóa (crypto, serialize)** | `find_transformations(session_id, ...)` | `get_execution_context` | Không dịch ngược WASM/minified JS bằng mắt |
| **Phân loại tham số Static vs Dynamic vs Nonce** | `differential_analysis(task_id)` | `compare_requests` | Không so sánh thủ công từng JSON payload |
| **Đồ thị quá nhiều file rác (CSS, ảnh, rác)** | `compact_graph(session_id, prune_static=True)` | `get_graph_statistics` | Không duyệt đồ thị nguyên bản gây tràn context |
| **Kiểm tra và tái phát lại Request** | `prepare_replay` $\rightarrow$ `validate_replay` $\rightarrow$ `execute_replay` | `resolve_dependencies` | Không bắn request trực tiếp mà bỏ qua validate |
| **Sinh mã nguồn độc lập (Python/cURL/TS)** | `synthesize_code(task_id, request_id, language="python")` | `explain_lineage_path` | Không tự gõ script mà không trích xuất dependency |
| **Đánh giá sau task & Đề xuất tiến hóa** | `record_task_retrospective(...)` | `get_tool_evolution_report` | **CẤM** kết thúc task mà không để lại hồi cứu |

---

## 3. Quy Trình Chuẩn 5 Bước (Standard Operating Procedure - SOP)

```
┌─────────────────────────────────────────────────────────────┐
│ Bước 1: Khám Phá & Định Vị (Discovery)                      │
│ get_task ──► list_sessions ──► list_requests                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Bước 2: Bóc Tách & Tinh Gọn (Dissection & Clean)            │
│ summarize_request ──► compact_graph ──► find_dependencies   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Bước 3: Phân Tích Lineage & Giải Mã Crypto                  │
│ trace_origin ──► find_transformations ──► differential_analysis │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Bước 4: Kiểm Chứng Replay & Sinh Mã Nguồn                   │
│ prepare_replay ──► validate_replay ──► synthesize_code      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Bước 5: Hồi Cứu Tiến Hóa Hệ Thống (Evolution)              │
│ record_task_retrospective ──► update_task_status('COMPLETED') │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Hướng Dẫn Cấu Hình MCP Cho Các Client Khác Nhau

### 4.1. Cấu hình cho Claude Desktop (`claude_desktop_config.json`)

Đường dẫn: `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "api_lineage": {
      "command": "d:\\source_code\\mcp_serve_reverse\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "app.main",
        "run-mcp",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

### 4.2. Cấu hình cho Cursor IDE (`.cursor/mcp.json`)

Tạo file `.cursor/mcp.json` tại thư mục gốc workspace:

```json
{
  "mcpServers": {
    "api_lineage": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "app.main", "run-mcp"]
    }
  }
}
```

### 4.3. Cấu hình cho Google Antigravity / Gemini CLI (`mcp_config.json`)

Trong thư mục cấu hình Antigravity IDE:

```json
{
  "mcpServers": {
    "api_lineage": {
      "command": "python",
      "args": ["-m", "app.main", "run-mcp"]
    }
  }
}
```
*(Kèm theo [instructions.md](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/instructions.py) làm knowledge rule).*

---

## 5. Nguyên Tắc Bảo Vệ Context Window & Redaction

1. **Giới hạn số lượng trả về**: Khi gọi `search_trace_events` hoặc `list_requests`, luôn truyền `limit` (từ 10 đến 50) và `offset` nếu cần phân trang.
2. **Cắt tỉa đồ thị trước khi truy vấn sâu**: Nếu một phiên lướt web có hàng trăm requests tĩnh, gọi `compact_graph(session_id, prune_static=True, prune_isolated=True)` trước khi gọi `get_graph_statistics` hoặc `trace_origin`.
3. **Tuân thủ Redaction**: Mặc định hệ thống che giấu bearer tokens và cookie passwords thành `[REDACTED]`. Không được cố tình tìm cách bypass cơ chế này lên console log để đảm bảo an toàn bí mật dữ liệu.
