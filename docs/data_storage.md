# 1. Nguyên tắc tổ chức dữ liệu trong DB

Với kiến trúc `api_lineage`, nên sử dụng SQLite với mô hình Hybrid Storage:

```
Relational Tables
    ├── sessions
    ├── trace_events
    ├── function_executions
    ├── network_requests
    ├── network_responses
    ├── storage_operations
    ├── graph_nodes
    └── graph_edges

JSON Columns
    ├── payload_json
    ├── properties_json
    ├── metadata_json
    └── evidence_json
```

Không nên lưu toàn bộ dữ liệu vào một bảng `events` hoặc một JSON khổng lồ. Cần:

* Bảng quan hệ: Các trường thường xuyên truy vấn, join và index.

* JSON: Metadata phụ thuộc adapter, dữ liệu chưa có schema ổn định.

* Graph tables: Truy vấn quan hệ giữa các thực thể.

* Raw event store: Giữ dữ liệu gốc để rebuild graph.

# 2. Tổng quan schema

```
sessions
   │
   ├── trace_events
   │      │
   │      └── function_executions
   │
   ├── network_requests ─── network_responses
   │          │
   │          └── graph_nodes
   │
   ├── storage_operations
   │          │
   │          └── graph_nodes
   │
   └── graph_edges
          │
          └── graph_nodes
```

Các bảng chính:

|
Nhóm

|

Bảng

|

Chức năng

|
| --- | --- | --- |
|

Session

|

`sessions`

|

Phiên capture

|
|

Event

|

`trace_events`

|

Event gốc

|
|

Runtime

|

`function_executions`

|

Lần gọi hàm

|
|

Network

|

`network_requests`

|

HTTP request

|
|

Network

|

`network_responses`

|

HTTP response

|
|

Storage

|

`storage_operations`

|

Đọc/ghi storage

|
|

Graph

|

`graph_nodes`

|

Các node

|
|

Graph

|

`graph_edges`

|

Quan hệ giữa node

|
|

Provenance

|

`edge_evidence`

|

Bằng chứng cho edge

|
|

Replay

|

`replay_plans`

|

Kế hoạch replay

|

# 3. Bảng `sessions`

Một session tương ứng với một lần chạy browser hoặc Android app.

SQL

```
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    name TEXT,
    target TEXT,
    status TEXT NOT NULL,

    started_at_ns INTEGER NOT NULL,
    ended_at_ns INTEGER,

    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sessions_source
ON sessions(source);

CREATE INDEX idx_sessions_started_at
ON sessions(started_at_ns);
```

Ví dụ:

JSON

```
{
  "id": "session-001",
  "source": "browser",
  "name": "Login flow",
  "target": "https://example.com",
  "status": "completed",
  "metadata": {
    "browser": "chromium",
    "platform": "linux"
  }
}
```

Các giá trị `source`:

```
browser
android
proxy
manual
```

# 4. Bảng `trace_events`

Đây là nguồn dữ liệu gốc, lưu mọi event sau khi chuẩn hóa.

SQL

```
CREATE TABLE trace_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp_ns INTEGER NOT NULL,

    execution_id TEXT,
    parent_execution_id TEXT,

    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Index quan trọng:

SQL

```
CREATE INDEX idx_events_session_time
ON trace_events(session_id, timestamp_ns);

CREATE INDEX idx_events_execution
ON trace_events(execution_id);

CREATE INDEX idx_events_type_time
ON trace_events(event_type, timestamp_ns);
```

### Tại sao cần lưu `trace_events`?

Ví dụ sau này bạn thay đổi thuật toán xác định `DERIVED_FROM`. Không cần capture lại browser, chỉ cần:

```
trace_events
      |
      v
New Graph Projector
      |
      v
Rebuild graph
```

# 5. Bảng `function_executions`

Không nên chỉ lưu function call trong JSON event. Các trường thường truy vấn nên được chuẩn hóa.

SQL

```
CREATE TABLE function_executions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    function_name TEXT,
    module_name TEXT,
    source_location TEXT,

    parent_execution_id TEXT,
    thread_id TEXT,
    process_id TEXT,

    started_at_ns INTEGER NOT NULL,
    ended_at_ns INTEGER,

    status TEXT,
    arguments_json TEXT,
    return_value_ref TEXT,
    stack_trace TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Ví dụ quan hệ:

```
buildPayload()
    |
    ├── argument: device_id
    ├── argument: timestamp
    └── return: request_body
```

`arguments_json` chỉ nên chứa dữ liệu đã được redaction hoặc reference tới value store.

# 6. Bảng Network

## 6.1. `network_requests`

SQL

```
CREATE TABLE network_requests (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    event_id TEXT,
    execution_id TEXT,

    method TEXT NOT NULL,
    url TEXT NOT NULL,
    url_template TEXT,

    host TEXT,
    path TEXT,
    query_json TEXT,

    headers_json TEXT NOT NULL DEFAULT '{}',
    body_json TEXT,

    started_at_ns INTEGER NOT NULL,
    completed_at_ns INTEGER,

    status TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Nên lưu thêm:

* `url_template`: `/api/users/{id}` để nhóm các request.

* `host`, `path`: giúp truy vấn nhanh.

* `body_json`: payload đã redaction.

* `execution_id`: context tạo request nếu có.

## 6.2. `network_responses`

SQL

```
CREATE TABLE network_responses (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,

    event_id TEXT,
    status_code INTEGER,

    headers_json TEXT NOT NULL DEFAULT '{}',
    body_json TEXT,

    received_at_ns INTEGER NOT NULL,
    body_hash TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (request_id)
        REFERENCES network_requests(id)
);
```

Quan hệ:

```
network_requests.id
        1
        │
        │
        0..1
        │
network_responses.request_id
```

Một request có thể không có response vì timeout, bị hủy hoặc lỗi mạng.

# 7. Bảng Value và Data Lineage

Đây là phần quan trọng nhất để theo dõi dữ liệu.

Nên tách value thành một entity độc lập thay vì chỉ lưu value trong request body.

## 7.1. `value_observations`

SQL

```
CREATE TABLE value_observations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    value_hash TEXT NOT NULL,
    value_type TEXT NOT NULL,
    value_length INTEGER,

    json_path TEXT,
    variable_name TEXT,

    sensitivity TEXT NOT NULL DEFAULT 'unknown',
    redacted_value TEXT,

    first_seen_at_ns INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Ví dụ:

```
value_id: value-001
value_hash: sha256:abc...
value_type: string
variable_name: access_token
sensitivity: secret
```

### Không nên dùng hash làm định danh duy nhất

Một giá trị giống nhau có thể xuất hiện trong nhiều session hoặc nhiều ngữ cảnh. Vì vậy:

* `id`: định danh observation.

* `value_hash`: dùng để so sánh hoặc liên kết giá trị.

* `session_id`: giới hạn phạm vi phân tích.

# 8. Graph Nodes

`graph_nodes` là lớp biểu diễn thống nhất của các thực thể.

SQL

```
CREATE TABLE graph_nodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    node_type TEXT NOT NULL,
    label TEXT,

    entity_id TEXT,
    properties_json TEXT NOT NULL DEFAULT '{}',

    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

### Các loại node

```
session
function_definition
function_execution
variable
value
transformation
http_request
http_response
header
query_parameter
body_field
storage
storage_entry
crypto_operation
```

### Ví dụ dữ liệu

JSON

```
{
  "id": "node:req-001",
  "session_id": "session-001",
  "node_type": "http_request",
  "label": "POST /api/action",
  "entity_id": "req-001",
  "properties": {
    "method": "POST",
    "path": "/api/action",
    "source": "browser"
  }
}
```

### Tại sao có `entity_id`?

Để node graph liên kết với entity gốc:

```
graph_nodes.entity_id
        |
        ├── network_requests.id
        ├── function_executions.id
        ├── value_observations.id
        └── storage_operations.id
```

SQLite không hỗ trợ foreign key đa hình trực tiếp, nên `entity_id` cần được kiểm soát ở application layer. Nếu cần ràng buộc nghiêm ngặt, có thể dùng các bảng liên kết riêng.

# 9. Graph Edges

SQL

```
CREATE TABLE graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,

    relation_type TEXT NOT NULL,

    confidence REAL NOT NULL DEFAULT 1.0,
    provenance_status TEXT NOT NULL,

    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id),

    FOREIGN KEY (source_id)
        REFERENCES graph_nodes(id),

    FOREIGN KEY (target_id)
        REFERENCES graph_nodes(id)
);
```

Index:

SQL

```
CREATE INDEX idx_edges_source_relation
ON graph_edges(source_id, relation_type);

CREATE INDEX idx_edges_target_relation
ON graph_edges(target_id, relation_type);

CREATE INDEX idx_edges_session_relation
ON graph_edges(session_id, relation_type);

CREATE INDEX idx_edges_confidence
ON graph_edges(confidence);
```

### Unique constraint nên có

Tránh tạo cùng một edge nhiều lần khi event được xử lý lại:

SQL

```
CREATE UNIQUE INDEX uq_graph_edge
ON graph_edges(
    session_id,
    source_id,
    target_id,
    relation_type
);
```

Nếu cùng một quan hệ có nhiều bằng chứng hoặc nhiều lần quan sát, nên lưu các bằng chứng riêng thay vì tạo nhiều edge trùng lặp.

# 10. Bảng Provenance

Nên tách bằng chứng khỏi `graph_edges` khi cần nhiều evidence cho một quan hệ.

SQL

```
CREATE TABLE edge_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    edge_id INTEGER NOT NULL,

    evidence_type TEXT NOT NULL,
    source_event_id TEXT,

    confidence REAL,
    explanation TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (edge_id)
        REFERENCES graph_edges(id),

    FOREIGN KEY (source_event_id)
        REFERENCES trace_events(event_id)
);
```

Ví dụ:

```
Edge:
  signature DERIVED_FROM device_id

Evidence:
  ├── argument_match
  ├── stack_trace
  └── value_hash_match
```

Cấu trúc này cho phép một edge có nhiều nguồn bằng chứng.

# 11. Bảng Storage Operations

SQL

```
CREATE TABLE storage_operations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    execution_id TEXT,

    storage_type TEXT NOT NULL,
    storage_scope TEXT,
    storage_key TEXT,

    operation TEXT NOT NULL,
    value_ref TEXT,

    timestamp_ns INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Các giá trị:

```
storage_type:
  local_storage
  session_storage
  cookie
  indexed_db
  shared_preferences
  sqlite
  memory

operation:
  read
  write
  delete
```

Ví dụ:

```
storage_operation
    |
    ├── storage_type: local_storage
    ├── storage_key: access_token
    ├── operation: read
    └── value_ref: value-001
```

# 12. Ví dụ dữ liệu hoàn chỉnh

Giả sử ứng dụng thực hiện:

JavaScript

```
const token = localStorage.getItem("access_token");

fetch("/api/action", {
  headers: {
    Authorization: `Bearer ${token}`
  }
});
```

Graph sẽ có:

```
┌────────────────────────────┐
│ Storage Entry              │
│ localStorage.access_token  │
└──────────────┬─────────────┘
               │ READS_FROM
               ▼
┌────────────────────────────┐
│ Value: access_token        │
└──────────────┬─────────────┘
               │ ATTACHES_TO
               ▼
┌────────────────────────────┐
│ Header: Authorization      │
└──────────────┬─────────────┘
               │ CONTAINS
               ▼
┌────────────────────────────┐
│ HTTP Request               │
│ POST /api/action           │
└────────────────────────────┘
```

Các bảng lưu:

```
storage_operations
    └── read: localStorage.access_token

value_observations
    └── value_hash: sha256:...

graph_nodes
    ├── storage_entry node
    ├── value node
    ├── header node
    └── request node

graph_edges
    ├── READS_FROM
    ├── ATTACHES_TO
    └── CONTAINS
```

# 13. Replay Schema

Chỉ nên triển khai sau khi lineage graph đã ổn định.

## `replay_plans`

SQL

```
CREATE TABLE replay_plans (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    target_request_id TEXT NOT NULL,

    status TEXT NOT NULL,
    policy_json TEXT NOT NULL DEFAULT '{}',

    created_at_ns INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

## `replay_steps`

SQL

```
CREATE TABLE replay_steps (
    id TEXT PRIMARY KEY,
    replay_plan_id TEXT NOT NULL,

    step_order INTEGER NOT NULL,
    step_type TEXT NOT NULL,

    target_node_id TEXT,
    dependencies_json TEXT NOT NULL DEFAULT '[]',

    status TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,

    FOREIGN KEY (replay_plan_id)
        REFERENCES replay_plans(id)
);
```

Các trạng thái:

```
planned
validated
blocked
approved
executed
failed
```

# 14. Tổ chức database theo giai đoạn

## MVP

```
sessions
trace_events
network_requests
network_responses
storage_operations
graph_nodes
graph_edges
edge_evidence
```

Chỉ cần các bảng này để xây dựng:

```
Request → Response
Response → Value
Value → Storage
Storage → Request
```

## Phase 2

Bổ sung:

```
function_executions
value_observations
runtime_variables
crypto_operations
```

Phục vụ:

```
argument tracking
return tracking
transformation detection
DERIVED_FROM inference
```

## Phase 3

Bổ sung:

```
replay_plans
replay_steps
search_documents
lineage_snapshots
```

# 15. Có nên sử dụng Neo4j không?

|
Tiêu chí

|

SQLite

|

Neo4j

|
| --- | --- | --- |
|

MVP local

|

Phù hợp

|

Hơi dư thừa

|
|

Dữ liệu vài session

|

Phù hợp

|

Phù hợp

|
|

Dễ backup

|

Rất dễ

|

Phức tạp hơn

|
|

Query graph sâu

|

Cần tự viết traversal

|

Mạnh

|
|

Triển khai đơn giản

|

Tốt

|

Cần service riêng

|
|

Mở rộng nhiều worker

|

Có giới hạn ghi đồng thời

|

Tốt hơn

|

Khuyến nghị: Bắt đầu với SQLite, nhưng thiết kế `GraphRepository` qua port:

Python

Chạy

```
class GraphRepository(Protocol):
    async def add_node(self, node: GraphNode) -> None:
        ...

    async def add_edge(self, edge: GraphEdge) -> None:
        ...

    async def get_neighbors(
        self,
        node_id: str,
        relation_types: list[str] | None = None,
    ) -> list[GraphNode]:
        ...

    async def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 8,
    ) -> list:
        ...
```

Sau này có thể thay implementation bằng PostgreSQL hoặc Neo4j mà không thay đổi application layer.

# 16. Những điểm cần tránh

1. Không lưu toàn bộ graph chỉ trong JSON. Khó index và truy vấn lineage.

2. Không coi mọi giá trị giống nhau là cùng một value. Cần session, thời điểm và context.

3. Không tạo edge `DERIVED_FROM` chỉ dựa trên call stack. Cần provenance và confidence.

4. Không xóa raw events sau khi dựng graph. Graph cần có khả năng rebuild.

5. Không lưu secret dạng plaintext trong graph. Sử dụng hash, redaction và secret store.

6. Không tạo graph node cho mọi ký tự hoặc mọi object nhỏ ngay từ MVP. Ưu tiên request field, storage entry, function argument và return value.

## Thiết kế được khuyến nghị

```
Raw Events
    ↓
Normalized Events
    ↓
Relational Entities
    ↓
Graph Nodes + Edges
    ↓
Provenance
    ↓
Graph Views
    ↓
MCP Query
```

Đây là mô hình phù hợp để bắt đầu với SQLite + Playwright, đồng thời vẫn mở rộng được sang Frida, PostgreSQL/Neo4j và hệ thống replay trong các giai đoạn tiếp theo.
