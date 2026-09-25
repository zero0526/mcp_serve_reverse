# 📋 BÁO CÁO TIẾN ĐỘ THỰC NGHIỆM: REQUEST-CENTRIC CAUSAL GRAPH (DEV)

> **Vị trí thực nghiệm:** `d:\source_code\mcp_serve_reverse\dev\`  
> **Thời điểm cập nhật:** 2026-09-25  
> **Trạng thái:** Đã hoàn thiện kiến trúc cốt lõi, chạy test 100% Passed, đã tích hợp CDP Passive Recorder.

---

## 🎯 1. Mục Tiêu & Chuyển Dịch Tư Duy (Paradigm Shift)

### Vấn đề của mô hình cũ:
- Mô hình ban đầu lấy `USER_EVENT` (Click, Input...) làm root. Điều này khiến đồ thị bị **lệch hướng sang User Analytics / RUM (Real User Monitoring)** thay vì phục vụ mục tiêu tối thượng: **API Reverse Engineering, Request Synthesis & Replay**.

### Mô hình mới: Request-Centric & Value-Flow Causal Graph
Trong Reverse Engineering, điểm bắt đầu (Root) của mọi câu hỏi luôn là **HTTP Request**:
1. **Backward Trace (Truy ngược Request)**:
   > *"Mỗi trường (field) trong Request (body, headers, cookies, tokens) được sinh ra từ đâu? Field nào lấy từ DOM, field nào đọc từ Cookie/Storage, field nào nằm trong thẻ `<script>` Server-Side Rendered (SSR), và field nào là kết quả tính toán của hàm JavaScript nào?"*
2. **Forward Trace (Truy xuôi Response)**:
   > *"Response trả về (JWT token, session id) được hàm nào bóc tách, lưu vào State nào (`localStorage`, `Cookie`) và kích hoạt những Request tiếp theo nào (`Authorization: Bearer ...`)?"*

```text
                     [SOURCE / STATE]
                (DOM, Storage, Cookie, Location)
                           │
                           ▼ READS
                       [VALUE] (Từng field / Token)
                           │
                           ▼ PASSES
                     [FUNCTION] (V8 Stack: buildPayload, encrypt)
                           │
                           ▼ BUILDS / SENDS
     ┌────────────────────────────────────────────────────────┐
     │                [REQUEST #N]  (TRACE ROOT)              │
     └────────────────────────────────────────────────────────┘
                           │
                           ▼ RESPONDS_TO
     ┌────────────────────────────────────────────────────────┐
     │                      [RESPONSE #N]                     │
     └────────────────────────────────────────────────────────┘
                           │
                           ▼ CONSUMES
                      [FUNCTION] (handleLogin, parseJSON)
                           │
                           ▼ WRITES / MUTATES
                     [STATE / SINK]
                 (localStorage["token"], DOM)
                           │
                           ▼ READS
                    [REQUEST #N+1] (Authorization: Bearer ...)
```

---

## 🛠️ 2. Những Gì Đã Làm Được (Completed in `dev/`)

### A. Schema Chuẩn Hóa [dev/schema.py](file:///d:/source_code/mcp_serve_reverse/dev/schema.py)
1. **5 Nhóm Node Chuyên Biệt**:
   - `RequestNode` (Root): Lưu `request_id`, `url`, `method`, `headers`, `query_params`, `body` (ValueRef), `initiator_stack` (V8 Call Stack).
   - `ResponseNode`: Lưu `status`, `mime_type`, `headers`, `body` (ValueRef), liên kết 1-1 với Request.
   - `ValueNode`: **Thành phần cốt lõi bị thiếu trước đây**. Cho phép phân rã payload thành từng field (`email`, `csrf_token`, `device_fp`), gắn mã băm SHA-256 để truy vết chính xác.
   - `StateNode`: Đại diện cho trạng thái môi trường (`DOM` input/script, `STORAGE`, `COOKIE`, `LOCATION`).
   - `FunctionNode`: Đại diện cho các hàm JS trong chuỗi V8 execution (`loginHandler`, `buildPayload`, `encrypt`).
2. **9 Quan Hệ Nhân Quả (CausalEdge)**:
   - Backward: `READS`, `PASSES`, `PRODUCES`, `BUILDS`, `SENDS`
   - Pair: `RESPONDS_TO`
   - Forward: `CONSUMES`, `WRITES`, `TRIGGERS`
3. **Minh Bạch Hóa Suy Luận**:
   - Mỗi cạnh đều gắn `confidence` (0.0 – 1.0), phân cấp `tier` (`DIRECT`, `STRONG`, `WEAK`) và danh sách `evidence` cụ thể (`["exact_value_match", "v8_initiator_stack"]`).
4. **2 API Truy Vấn Cốt Lõi**:
   - `trace_backward(request_id)`: Trả về cây phả hệ nguồn gốc của từng trường trong Request.
   - `trace_forward(response_id)`: Trả về cây tác động xuôi dòng của Response tới các State và Request tiếp theo.

### B. Bộ Lưu Trữ Tách Rời Payload [dev/storage.py](file:///d:/source_code/mcp_serve_reverse/dev/storage.py)
- Triển khai `ValueStore` và `ValueRef`:
  - Payload nhỏ ($< 4\text{ KB}$) được lưu inline preview và memory cache.
  - Payload lớn ($> 4\text{ KB}$) tự động offload ra đĩa tại `dev/blobs/<sha256>.bin`.
  - Giữ cho file JSON của đồ thị luôn siêu nhẹ ($\sim 14\text{ KB}$) dù phiên tương tác chứa các response HTML/JSON hàng megabytes.

### C. Bộ Dựng Đồ Thị & Tương Quan Nhân Quả [dev/graph.py](file:///d:/source_code/mcp_serve_reverse/dev/graph.py)
- Triển khai `CausalGraphBuilder`:
  - `build_request_lineage(request_node, post_data)`: Tự động bóc tách JSON / Form data thành các `ValueNode`, so khớp tìm về `StateNode` tương ứng (khớp exact value, token SSR trong thẻ `<script>`, Cookie trong headers).
  - Tự động dựng chuỗi V8 Function Call Stack nối vào Request.
  - `correlate_response_consumption(...)`: Thiết lập chuỗi Forward Trace khi Response được hàm JS bóc tách và lưu vào State.

### D. Bộ Kiểm Thử Thực Nghiệm 100% Passed [dev/test_pipeline.py](file:///d:/source_code/mcp_serve_reverse/dev/test_pipeline.py)
Kịch bản kiểm thử mô phỏng toàn bộ quy trình xác thực thực tế:
- **Khởi tạo State**: DOM hidden SSR CSRF token (`script#__NEXT_DATA__`), DOM input `email`, `password`, LocalStorage `device_fp`, Cookie `SESSION_ID`.
- **Request 1 (POST login)**:
  - `trace_backward` chứng minh 100% cả 5 trường đều truy ngược chính xác về đúng State gốc.
- **Response 1 (200 OK trả JWT)**:
  - `trace_forward` chứng minh token được hàm `handleLoginSuccess` trích xuất $\rightarrow$ ghi vào `localStorage["jwt_token"]` $\rightarrow$ truyền vào `Header: Authorization` của Request 2 (`GET /api/v1/user/me`).
- Kết quả: **Tất cả các bài test đều vượt qua 100%**.

### E. Tích Hợp CDP Passive Recorder [dev/cdb_explore.py](file:///d:/source_code/mcp_serve_reverse/dev/cdb_explore.py)
- Công cụ chạy ngầm bám theo tab Chrome đang mở (cổng 9222).
- Người dùng thao tác tự do trên trình duyệt. Khi nhấn `Ctrl + C`, script tự động:
  1. Xuất file log tuần tự: `dev/captured_sessions/session_flow_<ts>.json`.
  2. Dựng và xuất đồ thị nhân quả chuẩn hóa: `dev/captured_sessions/session_graph_<ts>.json`.

---

## 🔮 3. Kế Hoạch & Dự Định Tiếp Theo (Next Steps)

1. **Auto-Hooking JavaScript Boundary qua CDP (Không cần Extension)**:
   - Dùng `Page.addScriptToEvaluateOnNewDocument` để tiêm các hook nhẹ ghi nhận:
     - `Storage.prototype.setItem` & `getItem`
     - `document.cookie` setter & getter
     - Các thẻ `<script id="__NEXT_DATA__">` hoặc biến toàn cục SSR (`window.__INITIAL_STATE__`).
   - Giúp việc nhận diện nguồn gốc đạt độ tin cậy `DIRECT (1.0)` thay vì chỉ dựa vào khớp chuỗi.
2. **Đóng Gói Thành Bộ MCP Tools Mới**:
   - Nâng cấp các tool bị lỗi trong `mcp_serve_reverse` thành các tool chuyên biệt, mạnh mẽ:
     - `trace_request_lineage(request_id)`: Trả về cây nguồn gốc JSON/Mermaid của request.
     - `trace_response_impact(response_id)`: Hiển thị các request bị ảnh hưởng.
     - `synthesize_request_replay(request_id)`: Tự động sinh script Python tái hiện request kèm logic lấy token động từ các bước trước.
3. **Di Chuyển Từ `dev/` Vào Hệ Thống Chính `app/`**:
   - Khi các thử nghiệm trong `dev/` hoàn toàn ổn định và được người dùng đánh giá đạt yêu cầu, tiến hành refactor các domain models và storage trong `app/`.
