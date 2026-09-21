# Tóm tắt ý tưởng API Lineage MCP

## 1. Ý tưởng chung

Xây dựng một MCP Server phân tích và truy vết luồng dữ liệu của API.

Hệ thống bắt đầu từ việc quan sát hoạt động của ứng dụng:

* Trình duyệt thông qua Playwright.

* Android thông qua Frida trong giai đoạn mở rộng.

* HTTP Proxy hoặc các runtime instrumentation khác trong tương lai.

Mục tiêu là trả lời các câu hỏi như:

> Tham số này trong request được tạo ra từ đâu? Được xử lý qua những hàm nào? Có lấy từ response hoặc storage trước đó không? Nó được sử dụng ở các request nào tiếp theo?

Thay vì chỉ lưu request/response dạng log, hệ thống chuyển toàn bộ dữ liệu quan sát được thành đồ thị quan hệ và nguồn gốc dữ liệu (Data Lineage Graph) để LLM truy vấn dễ dàng.

## 2. Giải pháp kiến trúc

Sử dụng kết hợp các mô hình kiến trúc:

|
Giải pháp

|

Vai trò

|
| --- | --- |
|

Hexagonal Architecture

|

Tách domain khỏi Playwright, Frida, SQLite và MCP

|
|

Event-Driven Architecture

|

Chuẩn hóa mọi hoạt động thành `TraceEvent`

|
|

Property Graph

|

Biểu diễn hàm, request, response, value và storage

|
|

Event Sourcing nhẹ

|

Lưu event gốc để có thể dựng lại graph

|
|

Projection Pattern

|

Chuyển event thành node và edge

|
|

CQRS-like separation

|

Tách quá trình ghi trace khỏi truy vấn lineage

|
|

MCP Tool Layer

|

Cung cấp truy vấn ngữ nghĩa đơn giản cho LLM

|
|

Strategy/Adapter Pattern

|

Hỗ trợ nhiều nguồn capture khác nhau

|

Luồng tổng quát:

```
Browser / Android / Proxy
          |
          v
    Capture Adapter
          |
          v
     TraceEvent
          |
          v
   Event Normalization
          |
          v
    Graph Projection
          |
          v
 Event Store + Graph Store
          |
          v
   Graph Query Service
          |
          v
       MCP Server
          |
          v
          LLM
```

## 3. Tổ chức dữ liệu

### 3.1. Event — dữ liệu gốc

Lưu các hoạt động quan sát được:

```
function.entered
function.exited
function.argument
function.return
network.request
network.response
storage.read
storage.write
crypto.input
crypto.output
runtime.variable
```

Mỗi event có:

```
event_id
session_id
source
event_type
timestamp_ns
execution_id
parent_execution_id
payload
metadata
```

Event là nguồn dữ liệu gốc. Graph có thể được rebuild khi thuật toán projection thay đổi.

### 3.2. Node — thực thể trong đồ thị

```
Session
Function Definition
Function Execution
Variable
Value
Transformation
HTTP Request
HTTP Response
Header
Query Parameter
Body Field
Storage
Storage Entry
Crypto Operation
```

Ví dụ:

```
Function: buildPayload
        |
        v
Value: device_id
        |
        v
HTTP Request: POST /api/action
```

### 3.3. Edge — quan hệ giữa các node

```
CALLS
RETURNS
PRODUCES
CONSUMES
DERIVED_FROM
TRANSFORMS
EXTRACTS
USED_IN
ATTACHES_TO
STORES_IN
READS_FROM
PRECEDES
```

Ví dụ:

```
Response
   |
   | EXTRACTS
   v
access_token
   |
   | STORES_IN
   v
localStorage
   |
   | READS_FROM
   v
attachAuthHeader()
   |
   | ATTACHES_TO
   v
Next Request
```

### 3.4. Provenance — độ tin cậy

Mỗi quan hệ cần thể hiện nguồn bằng chứng:

```
status:
  observed
  inferred
  unknown

evidence:
  direct_observation
  stack_trace
  argument_match
  return_match
  value_hash_match
  static_analysis
  heuristic
```

Ví dụ:

JSON

```
{
  "relation": "DERIVED_FROM",
  "status": "inferred",
  "confidence": 0.82,
  "evidence": [
    "argument_match",
    "stack_trace"
  ]
}
```

Điều này giúp LLM phân biệt dữ liệu quan sát trực tiếp và suy luận.

## 4. Các tầng dữ liệu

```
┌─────────────────────────────────┐
│ Raw Trace Events                │
│ Dữ liệu capture nguyên bản      │
└───────────────┬─────────────────┘
                v
┌─────────────────────────────────┐
│ Normalized Events               │
│ Schema thống nhất               │
└───────────────┬─────────────────┘
                v
┌─────────────────────────────────┐
│ Property Graph                  │
│ Nodes + Edges + Provenance      │
└───────────────┬─────────────────┘
                v
┌─────────────────────────────────┐
│ Graph Views                     │
│ Request / Lineage / Storage     │
└───────────────┬─────────────────┘
                v
┌─────────────────────────────────┐
│ MCP Query Results               │
│ Kết quả ngắn gọn cho LLM        │
└─────────────────────────────────┘
```

### Graph Views

Không đưa toàn bộ graph vào prompt. Tạo các view:

* `RequestView`: tổng quan request và dependency.

* `LineageView`: nguồn gốc và downstream của value.

* `ExecutionView`: trình tự gọi hàm.

* `StorageView`: đọc/ghi storage.

* `ReplayView`: dependency và thứ tự thực thi.

## 5. Tổ chức thư mục cốt lõi

```
app/
├── domain/
│   ├── trace/          # TraceEvent, provenance
│   ├── graph/          # Node, Edge, Relation, Projection
│   ├── network/        # Request, Response
│   ├── storage/        # Storage entities
│   └── replay/         # Replay model và policy
│
├── application/
│   ├── ingest/         # Nhận và chuẩn hóa event
│   ├── graph/          # Project và rebuild graph
│   ├── lineage/        # Trace origin/downstream
│   ├── trace/          # Timeline và event search
│   └── replay/         # Dependency và replay planning
│
├── ports/
│   ├── event_store.py
│   ├── graph_repository.py
│   ├── capture.py
│   ├── runtime.py
│   └── replay.py
│
├── adapters/
│   ├── browser/        # Playwright + JavaScript hooks
│   ├── android/        # Frida
│   ├── persistence/    # SQLite
│   └── llm/            # LLM integration
│
└── interfaces/
    └── mcp/
        ├── server.py
        ├── tools/
        └── resources/
```

## 6. Các phase triển khai chính

### Phase 1: Capture và Event Store

Mục tiêu: Ghi nhận dữ liệu từ browser.

Các thành phần:

* Playwright network capture.

* `fetch.js`, `xhr.js`.

* Storage instrumentation.

* `TraceEvent`.

* SQLite Event Store.

Kết quả: có timeline và raw trace đáng tin cậy.

### Phase 2: Graph Projection

Mục tiêu: Chuyển event thành graph.

```
TraceEvent
    → Projector
    → GraphMutation
    → GraphRepository
```

Bắt đầu với:

```
Request ↔ Response
Request ↔ Function Execution
Response ↔ Extracted Value
Value ↔ Storage
Storage ↔ Next Request
```

### Phase 3: Lineage Analysis

Mục tiêu: Truy vấn nguồn gốc dữ liệu.

```
trace_origin()
trace_downstream()
find_consumers()
find_transformations()
get_request_dependencies()
```

Bổ sung argument, return value và crypto instrumentation để suy luận `DERIVED_FROM`.

### Phase 4: MCP Query Layer

Mục tiêu: Cho LLM truy vấn graph thông qua các tool có ngữ nghĩa.

Không cho LLM truy vấn SQL hoặc graph traversal tùy ý ngay từ đầu. MCP sẽ kiểm soát:

```
max_depth
max_nodes
max_paths
session_id
time_range
relation_types
```

### Phase 5: Replay

Mục tiêu: Chuẩn bị và kiểm tra khả năng replay dựa trên dependency graph.

```
Target Request
      |
      v
Find Dependencies
      |
      v
Resolve Value Origins
      |
      v
Build Replay Plan
      |
      v
Validate Policy
      |
      v
Execute with Authorization
```

### Phase 6: Android/Frida

Frida chuyển các hook event về cùng schema:

```
Frida Hook
    → Android Adapter
    → TraceEvent
    → Common Graph Projector
```

Không tạo graph schema riêng cho Android.

## 7. Các phrase chính để triển khai

### Kiến trúc

* `Hexagonal Architecture`

* `Ports and Adapters`

* `Event-Driven Architecture`

* `Domain-Driven Design`

* `Separation of Concerns`

* `CQRS-like Read/Write Separation`

### Thu thập dữ liệu

* `Browser Instrumentation`

* `Playwright Network Capture`

* `JavaScript Runtime Instrumentation`

* `Android Frida Hooking`

* `Trace Event Normalization`

* `Execution Context Tracking`

### Đồ thị và truy vết

* `Property Graph`

* `Data Lineage Graph`

* `Provenance Tracking`

* `Graph Projection`

* `Dependency Graph`

* `Runtime Data Flow Analysis`

* `Backward/Forward Taint Analysis`

* `Value Origin Tracking`

* `Graph Traversal`

* `Subgraph Extraction`

### LLM và MCP

* `MCP Server`

* `Semantic Graph Query`

* `Graph View`

* `Structured Tool Output`

* `LLM-Friendly Query Interface`

* `Context Reduction`

* `Evidence-Based Explanation`

### Replay

* `Dependency-Aware Replay`

* `Replay Planning`

* `Replay Validation`

* `Execution Policy`

* `Missing Dependency Detection`

* `Request Reconstruction`

## 8. MVP nên tập trung vào đâu?

```
MVP
├── Playwright capture
├── Unified TraceEvent
├── SQLite Event Store
├── SQLite Graph Store
├── Request/Response Graph
├── Storage Lineage
├── Provenance Metadata
├── trace_origin MCP tool
├── get_request_dependencies MCP tool
└── get_session_timeline MCP tool
```

Chưa cần triển khai ngay:

* Neo4j.

* Vector database.

* Tự động replay mọi request.

* Phân tích đầy đủ JavaScript AST.

* Dynamic taint tracking hoàn chỉnh.

* LLM tự suy luận không giới hạn.

Tóm lại: Hệ thống của bạn là một Runtime API Data Lineage Platform, trong đó event là dữ liệu gốc, Property Graph là mô hình quan hệ, Graph View là lớp tối ưu cho LLM, còn MCP cung cấp các truy vấn lineage và dependency có kiểm soát.
