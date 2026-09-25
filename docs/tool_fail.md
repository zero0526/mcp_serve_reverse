

Đã hoàn thành kiểm thử toàn diện **35/35 MCP Tools** của server `api_lineage` (`mcp_serve_reverse`) trên dữ liệu thực tế của task [task_4191a786](file:///d:/source_code/mcp_serve_reverse/app) (phiên `sess_task_4191a786_1`, trọng tâm request POST [evt_req_bd5ad7c122](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/tools/network.py)).

Dưới đây là báo cáo phân tích, kiểm thử và đánh giá chi tiết:

---

# 📊 BẢNG TỔNG HỢP KIỂM THỬ 35 TOOLS

| Phân nhóm chức năng | Tổng số tool | Hoạt động tốt | Bị lỗi (Fatal Bug) | Kết quả kém kỳ vọng / Hạn chế |
| :--- | :---: | :---: | :---: | :---: |
| **1. Quản lý Task & Tiến hóa (Task & Evolution)** | 5 | 5 | 0 | 0 |
| **2. Thu thập & Giám sát (Capture & Observation)** | 5 | 5 | 0 | 0 |
| **3. Truy vết Sự kiện & Runtime (Trace & Execution)** | 3 | 2 | 0 | 1 (`get_execution_context`) |
| **4. Đồ thị Tri thức Lineage (Knowledge Graph)** | 8 | 7 | 0 | 1 (`trace_origin`) |
| **5. Phân tích Mạng HTTP (Network & Differential)** | 6 | 3 | 2 (`diff_analysis`, `compare_req`) | 1 (`analyze_request_lineage`) |
| **6. Phát lại & Tái tạo Mã nguồn (Replay & Synthesis)** | 8 | 4 | 2 (`prepare_replay`, `synthesize_code`) | 2 (`execute_replay`, `transformations`) |
| **TỔNG CỘNG** | **35** | **26** | **4** | **5** |

---

# 🚨 NHÓM TOOL BỊ LỖI NGHIÊM TRỌNG (FATAL BUGS)

### 1. `synthesize_code` — Sinh mã nguồn lỗi cú pháp & runtime không thể chạy được
* **Mức độ:** 🔴 **Nghiêm trọng (Critical Flaw)**
* **Kiểm thử trên request:** `evt_req_bd5ad7c122` (POST `ExamProcess.php`).
* **Các lỗi phát hiện trong mã sinh ra:**
  1. **NameError Runtime:** Sinh f-string `":authority": f"Bearer {auth_token}"` trong khi hàm `async def execute_request(client=None)` **không hề có tham số `auth_token`**. Chạy code sẽ lập tức văng `NameError: name 'auth_token' is not defined`.
  2. **Crash HTTP/2 Pseudo-headers:** Giữ nguyên các pseudo-headers `:authority`, `:path`, `:method`, `:scheme` đưa vào từ điển `headers`. Khi chạy với `httpx` hoặc `requests`, thư viện sẽ crash hoặc server từ chối request (`InvalidHeader`).
  3. **Sai lệch kiểu dữ liệu Body:** Request gốc là `application/x-www-form-urlencoded` với chuỗi `questnbr=1&showall=1...`, nhưng hàm lại gọi `client.request(..., json=payload)`. Việc này biến payload thành chuỗi JSON `"\"questnbr=1...\""` và tự đổi header sang `application/json`, khiến server không nhận được form data.
  4. **Hardcoded Hash Redaction:** Header Cookie bị ghi cứng chuỗi hash `[REDACTED:sha256:ec1dc6f85fb3ae50]`.
* **Vị trí code lỗi:** [`app/adapters/synthesis/code_synthesizer.py:40-93`](file:///d:/source_code/mcp_serve_reverse/app/adapters/synthesis/code_synthesizer.py#L40-L93).

---

### 2. `prepare_replay` — Ghi đè hỏng header `:authority` thành Token giả mạo
* **Mức độ:** 🔴 **Lỗi Logic Nghiêm trọng**
* **Hiện tượng:** Header gốc của request là `:authority: watermarkexams.com`. Sau khi qua `prepare_replay`, header bị biến dạng thành:
  ```json
  ":authority": "Bearer mock_auth_token"
  ```
  *(Lỗi này lây truyền trực tiếp sang cả `execute_replay` và `synthesize_code`).*
* **Nguyên nhân:** Trong [`GenerateReplaySpecUseCase`](file:///d:/source_code/mcp_serve_reverse/app/application/lineage/generate_replay_spec.py#L88-L93):
  ```python
  for h_key, h_val in headers.items():
      h_key_lower = h_key.lower()
      if "auth" in h_key_lower or "token" in h_key_lower:
          headers_template[h_key] = "Bearer {{auth_token}}"
  ```
  Tên header HTTP/2 `:authority` vô tình chứa chuỗi con `"auth"`, khiến hệ thống tưởng đây là header xác thực và thay thế bằng `Bearer {{auth_token}}`, sau đó `VariableResolver` điền giá trị `mock_auth_token`!

---

### 3. `differential_analysis` — Redaction che giấu nhầm cả số liệu thống kê
* **Mức độ:** 🟠 **Lỗi Data Masking**
* **Hiện tượng:** Khi phân tích vi phân, metric tổng số token trong kết quả trả về bị che mất:
  ```json
  "token_count": "[REDACTED]"
  ```
* **Nguyên nhân:** Hàm [`redact_sensitive_payload`](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/schemas/responses.py#L43-L46) kiểm tra:
  ```python
  is_sensitive = k_lower in SENSITIVE_KEYS or any(
      s in k_lower for s in ["token", "secret", "password", "api_key", "apikey"]
  )
  ```
  Bất kỳ key nào chứa chữ `token` (như `token_count`, `token_length`, `token_type`) đều bị coi là token nhạy cảm và gán thành `[REDACTED]` dù giá trị là số đếm `int`.

---

### 4. `compare_requests` — Schema tham số quá cứng nhắc gây lỗi Agent
* **Mức độ:** 🟡 **Lỗi Validation / Trải nghiệm gọi Tool**
* **Hiện tượng:** Khi Agent muốn so sánh 2 request trong cùng session và truyền `session_id`, `left_request_id`, `right_request_id` (hoặc `base_request_id`, `target_request_id`), tool lập tức ném lỗi Pydantic validation:
  `Field required: left_session_id, right_session_id`.
* **Nguyên nhân:** [`compare_requests_tool`](file:///d:/source_code/mcp_serve_reverse/app/interfaces/mcp/tools/network.py#L131-L137) bắt buộc phải truyền đủ 4 tham số riêng biệt, không hỗ trợ fallback `session_id` dùng chung cho cả 2 vế.

---

# ⚠️ NHÓM TOOL CHO KẾT QUẢ KHÔNG NHƯ KỲ VỌNG / HẠN CHẾ

### 1. `trace_origin` & `analyze_request_lineage` — Đứt gãy nguồn gốc tham số HTML Form
* **Hiện tượng:** Khi truy vết `csrf_token` hoặc `currindex_hidden` của request POST, `trace_origin` trả về:
  ```json
  "paths": [], "status": "COMPLETED"
  ```
  `analyze_request_lineage` cũng trả về `sources: []`.
* **Nguyên nhân gốc:** Giá trị `csrf_token` này được server trả về trong thẻ `<input type="hidden" name="csrf_token" value="...">` của trang HTML trước đó (GET `ExamProcess.php?exam=307`). Tuy nhiên, `GraphProjector` hiện tại chỉ bóc tách JSON và Cookie, chưa có module parse HTML DOM Form inputs để tạo node nguồn trên đồ thị.

### 2. `find_transformations` — Bắt nhầm telemetry lỗi JS thành biến đổi dữ liệu
* **Hiện tượng:** Báo cáo 10 biến đổi `JSON.stringify` liên kết vào `headers.origin`.
* **Thực tế:** Đây là do trang web bị lỗi `ReferenceError: bootstrap is not defined`, đoạn mã bridge bắt ngoại lệ JS rồi serialize gửi về backend capture. Tool dùng heuristic thời gian nên đã gắn nhầm sự kiện telemetry lỗi này vào request HTTP.

### 3. `get_execution_context` — Bất khả dụng trong phiên Capture thông thường
* **Hiện tượng:** Khi gọi với bất kỳ sự kiện nào đều trả về `NOT_FOUND` hoặc rỗng (`total_count: 0`).
* **Thực tế:** Trong chế độ capture browser mặc định, tính năng hook/profiler chi tiết từng hàm JS không được kích hoạt để tránh làm sập trình duyệt, nên sự kiện `function_execution` không hề tồn tại. Tool này trở thành "dead tool" đối với phần lớn các session thực tế.

### 4. `list_requests` — Thông tin HTTP tĩnh chưa chuẩn
* **Hiện tượng:** Đối với các tài nguyên như SVG, CSS, JS bundle, tool trả về `method: "UNKNOWN"` và `path: null`. Dù là static asset nhưng method thực tế vẫn là `GET`.

---

# 📋 ĐÁNH GIÁ ĐỀ XUẤT: LOẠI BỎ - GIỮ NGUYÊN - NÂNG CẤP

### 1. Nhóm GIỮ NGUYÊN (Keep as-is - 21 Tools)
Hoạt động rất ổn định, nhanh và đáp ứng đúng thiết kế:
* **Task & Lifecycle:** `get_task`, `list_tasks`, `update_task_status`, `record_task_retrospective`, `get_tool_evolution_report`, `get_capture_status`, `list_sessions`, `stop_capture_session`.
* **Trace Timeline & Search:** `search_trace_events`, `get_trace_timeline`.
* **Graph Queries & Management:** `get_graph_statistics`, `get_graph_node`, `get_graph_neighbors`, `rebuild_graph`, `compact_graph`, `trace_downstream`, `explain_lineage_path`, `compare_lineage`.
* **Network & Replay Safety:** `summarize_request`, `find_request_dependencies`, `validate_replay`.

---

### 2. Nhóm CẦN SỬA LỖI & NÂNG CẤP (Fix & Upgrade - 9 Tools)

| Tool | Hành động nâng cấp cần thực hiện |
| :--- | :--- |
| **`prepare_replay`** | Loại bỏ HTTP/2 pseudo-headers (`:authority`, `:path`...), sửa logic `if "auth" in h_key.lower()` thành so sánh chính xác `h_key.lower() in ("authorization", "x-api-key")`. Chuyển `:authority` thành `Host`. |
| **`synthesize_code`** | 1. Tự động thêm các biến template vào argument của hàm Python để tránh `NameError`.<br>2. Lọc bỏ pseudo-headers.<br>3. Kiểm tra Content-Type: nếu là `application/x-www-form-urlencoded` thì dùng `data=payload` thay vì `json=payload`.<br>4. Biến Cookie thành `os.getenv("SESSION_COOKIE")` thay vì hardcode hash redacted. |
| **`differential_analysis`** | 1. Sửa hàm `redact_sensitive_payload` bỏ qua các key thống kê kết thúc bằng `_count`, `_len`, `_length`, `_type`.<br>2. Bổ sung chế độ phân tích vi phân nội tại (intra-session differential analysis) giữa các request tuần tự trong cùng 1 session khi chỉ có 1 session. |
| **`compare_requests`** | Bổ sung fallback `session_id` (nếu truyền `session_id` thì tự gán cho cả `left_session_id` và `right_session_id`). Thêm alias `base_request_id` / `target_request_id`. |
| **`trace_origin` & `analyze_request_lineage`** | Bổ sung **HTML Form Parser** trong `GraphProjector`: quét các thẻ `<input type="hidden">`, `<meta name="csrf-token">` trong response HTML để tạo node dữ liệu nguồn, khôi phục đường truyền cho CSRF Token. |
| **`find_transformations`** | Thêm bộ lọc loại bỏ các hàm serialize thuộc về telemetry nội bộ (`__api_lineage_bridge__`, `runtime_error`). |
| **`resolve_dependencies`** | Hiện tại tool đã tìm được prerequisite GET rất tốt. Cần nâng cấp thêm trích xuất biến từ HTML response (ngoài response header `set-cookie`). |
| **`execute_replay`** | Thừa hưởng các bản vá từ `prepare_replay` để chạy replay thực tế không bị lỗi HTTP 400. |

---

### 3. Nhóm ĐỀ XUẤT LOẠI BỎ HOẶC ĐÓNG GÓI THÀNH INTERNAL HELPER (Deprecate / Merge - 5 Tools)

1. **`get_execution_context` $\rightarrow$ Đóng gói / Giấu khỏi danh sách mặc định:**
   * Vì hầu hết các session capture qua browser không trace cấp độ AST từng hàm JS (gây crash/lag). Tool này luôn gây lúng túng cho Agent khi gọi và nhận `NOT_FOUND`. Chỉ nên bật khi chạy session ở chế độ `--deep-profile`.
2. **`get_blob_content` $\rightarrow$ Merge vào `summarize_request`:**
   * Agent gần như không bao giờ biết mã hash SHA-256 của blob để gọi độc lập. `summarize_request` hiện đã có sẵn inline/preview blob content.
3. **`detect_security_challenges` $\rightarrow$ Nâng cấp hoặc merge vào `summarize_request`:**
   * Bộ luật hiện tại quá đơn sơ (chỉ regex vài chữ "cloudflare", "captcha"). Nếu không mở rộng signature WAF/Bot thì nên đưa cảnh báo này trực tiếp vào metadata của `summarize_request`.
4. **`synthesize_code` $\rightarrow$ Nâng cấp tiến hóa thành `synthesize_workflow`:**
   * Thực tế reverse-engineer không bao giờ chỉ chạy 1 request lẻ loi mà cần một chuỗi: *Khởi tạo session $\rightarrow$ Lấy CSRF từ GET $\rightarrow$ POST dữ liệu $\rightarrow$ Trích xuất kết quả*. Cần nâng cấp tool này thành bộ sinh script workflow hoàn chỉnh.
5. **`start_capture_session`:**
   * Cần có cờ bảo vệ tài nguyên hoặc chạy async có timeout rõ ràng, tránh để Agent treo khi browser khởi động trên môi trường headless.

---

Bạn có muốn tôi tiến hành thực hiện ngay các bản sửa lỗi (Fixes) cho **`prepare_replay`**, **`synthesize_code`**, **`differential_analysis`** và **`compare_requests`** trên mã nguồn `mcp_serve_reverse` không?