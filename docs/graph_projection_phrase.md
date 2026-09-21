# Phase 2: Graph Projection

## 1. Mục tiêu của Phase 2

Phase 1 — Capture & Event Store lưu lại những gì xảy ra trong trình duyệt dưới dạng các event rời rạc:

```
function_call
network_request
network_response
storage_read
storage_write
serialize
deserialize
...
```

Những event này hữu ích cho việc debug, nhưng chưa trả lời trực tiếp được các câu hỏi:

* Giá trị `token` được tạo ra từ đâu?

* Tham số `sign` của request được tính bằng hàm nào?

* Dữ liệu trong `localStorage` được sử dụng để tạo request nào?

* Request B có sử dụng kết quả từ request A không?

* Hàm `generateSignature()` nhận đầu vào nào và trả về giá trị nào?

* Một giá trị xuất hiện trong response được truyền qua những hàm nào trước khi gửi đi?

Phase 2 chuyển event log thành một đồ thị quan hệ có cấu trúc.

```
Raw Events
    │
    ▼
Normalization
    │
    ▼
Entity & Value Extraction
    │
    ▼
Node Projection
    │
    ▼
Edge Inference
    │
    ▼
Graph Validation
    │
    ▼
Queryable Trace Graph
```

Kết quả mong muốn:

```
Storage Read
    │
    │ produces
    ▼
Value: user_id
    │
    │ consumed_by
    ▼
Function: buildRequestParams()
    │
    │ returns
    ▼
Value: sign
    │
    │ used_in
    ▼
Network Request: POST /api/order
```

# 2. Phạm vi Phase 2

Phase 2 nên tập trung vào projection có bằng chứng, không cố gắng suy luận toàn bộ logic ứng dụng ngay từ đầu.

## 2.1. Những gì Phase 2 cần làm

|
Nhóm

|

Công việc

|
| --- | --- |
|

Node projection

|

Chuyển event thành node

|
|

Value identity

|

Nhận diện các giá trị giống nhau giữa event

|
|

Edge projection

|

Tạo quan hệ giữa node

|
|

Execution linking

|

Liên kết function call/return

|
|

Network linking

|

Liên kết function với request

|
|

Storage linking

|

Liên kết storage với execution

|
|

Temporal ordering

|

Bảo đảm quan hệ theo thời gian

|
|

Provenance

|

Lưu bằng chứng cho từng cạnh

|
|

Query

|

Truy vấn nguồn gốc và luồng dữ liệu

|
|

Validation

|

Kiểm tra graph không tạo quan hệ sai rõ ràng

|

## 2.2. Những gì chưa nên làm

Chưa nên thực hiện toàn bộ các công việc sau trong Phase 2:

* Suy luận chính xác toàn bộ call graph của JavaScript.

* Khẳng định một giá trị được truyền qua một hàm khi không có bằng chứng.

* Tự động giải mã mọi dữ liệu mã hóa.

* Xác định chắc chắn thuật toán chữ ký chỉ từ một chuỗi đầu ra.

* Replay request.

* Tự động sửa request hoặc thay đổi trạng thái trình duyệt.

* Hook toàn bộ function trong mọi thư viện.

Những phần này nên thuộc Phase 3 hoặc các phase chuyên biệt về data lineage, analysis và replay.

# 3. Kiến trúc Phase 2

```
                    ┌────────────────────┐
                    │   Event Store      │
                    │ SQLite + JSONL     │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Event Normalizer   │
                    └─────────┬──────────┘
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
    ┌────────────────┐ ┌──────────────┐ ┌─────────────────┐
    │ Node Projector │ │ Value Indexer │ │ Evidence Store  │
    └───────┬────────┘ └──────┬───────┘ └────────┬────────┘
            └─────────────────┼─────────────────┘
                              ▼
                    ┌────────────────────┐
                    │ Edge Projector     │
                    │ Rule-based         │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Graph Validator    │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Graph Store        │
                    └────────────────────┘
```

Nên tách thành các module độc lập:

```
app/
  application/
    graph/
      project_session.py
      project_events.py
      rebuild_graph.py
      validate_graph.py
      query_graph.py

  domain/
    graph/
      nodes.py
      edges.py
      graph_model.py
      value_identity.py
      evidence.py
      confidence.py
      projection_rules.py

  infrastructure/
    graph/
      sqlite_graph_store.py
      graph_indexes.py
      graph_serializer.py

  adapters/
    graph/
      event_to_node.py
      execution_projector.py
      network_projector.py
      storage_projector.py
      value_matcher.py
      edge_inference.py
```

# 4. Thiết kế Graph Model

## 4.1. Node là gì?

Node đại diện cho một thực thể hoặc sự kiện có thể được truy vấn trong trace.

Các loại node ban đầu:

```
SESSION
PAGE
FRAME
EXECUTION
NETWORK_REQUEST
NETWORK_RESPONSE
STORAGE_OPERATION
VALUE
SERIALIZATION
ERROR
```

Ví dụ:

JSON

```
{
  "node_id": "exec:01HXYZ",
  "node_type": "EXECUTION",
  "session_id": "session-001",
  "properties": {
    "function_name": "buildRequestParams",
    "page_id": "page-001",
    "frame_id": "frame-main",
    "status": "RETURN",
    "started_at_ns": 1000,
    "ended_at_ns": 2000
  }
}
```

### Nguyên tắc

Mỗi node phải có:

* ID ổn định.

* Loại node.

* `session_id`.

* Thời điểm hoặc khoảng thời gian.

* Reference tới event gốc.

* Metadata.

* Thông tin độ tin cậy nếu node được suy luận.

Không nên sử dụng nội dung payload làm ID duy nhất vì hai event khác nhau có thể có cùng payload.

## 4.2. Edge là gì?

Edge biểu diễn quan hệ giữa hai node.

Ví dụ:

```
Execution A ──returns──> Value X
Value X ──consumed_by──> Execution B
Execution B ──initiates──> Network Request C
Network Request C ──has_response──> Network Response D
```

Một edge nên có cấu trúc:

JSON

```
{
  "edge_id": "edge-001",
  "session_id": "session-001",
  "source_node_id": "exec:001",
  "target_node_id": "value:abc",
  "edge_type": "RETURNS",
  "confidence": 1.0,
  "evidence": [
    {
      "event_id": "event-001",
      "reason": "Function return value"
    }
  ],
  "inferred": false,
  "created_at_ns": 3000
}
```

### Các loại edge nên hỗ trợ

|
Edge

|

Ý nghĩa

|
| --- | --- |
|

`CONTAINS`

|

Session chứa page hoặc execution

|
|

`PARENT_OF`

|

Execution cha chứa execution con

|
|

`CALLS`

|

Một execution gọi execution khác

|
|

`RETURNS`

|

Execution tạo ra giá trị trả về

|
|

`THROWS`

|

Execution tạo ra exception

|
|

`READS`

|

Execution đọc storage

|
|

`WRITES`

|

Execution ghi storage

|
|

`CONSUMES`

|

Execution sử dụng value

|
|

`PRODUCES`

|

Execution tạo value

|
|

`INITIATES`

|

Execution khởi tạo request

|
|

`HAS_RESPONSE`

|

Request có response

|
|

`SERIALIZES`

|

Value được serialize

|
|

`DESERIALIZES`

|

Dữ liệu được deserialize

|
|

`PRECEDES`

|

Node xảy ra trước node khác

|
|

`CORRELATES_WITH`

|

Hai event được liên kết theo correlation

|
|

`DUPLICATE_OF`

|

Event trùng hoặc tương ứng với event khác

|

Không nên đưa tất cả quan hệ vào một loại `RELATED_TO`, vì sẽ làm mất ý nghĩa ngữ nghĩa và khó truy vấn.

# 5. Node Projection

## 5.1. Từ event thành node

Không phải mọi event đều cần tạo một node riêng. Cần quy định mapping rõ ràng.

|
Event Phase 1

|

Node Phase 2

|
| --- | --- |
|

`page_created`

|

`PAGE`

|
|

`framenavigated`

|

`PAGE` hoặc `NAVIGATION`

|
|

`function_call`

|

`EXECUTION`

|
|

`function_return`

|

Cập nhật `EXECUTION`, tạo `VALUE` nếu cần

|
|

`function_throw`

|

`ERROR` và cập nhật execution

|
|

`network_request`

|

`NETWORK_REQUEST`

|
|

`network_response`

|

`NETWORK_RESPONSE`

|
|

`storage_read`

|

`STORAGE_OPERATION` và `VALUE`

|
|

`storage_write`

|

`STORAGE_OPERATION` và `VALUE`

|
|

`serialize`

|

`SERIALIZATION`

|
|

`deserialize`

|

`SERIALIZATION`

|
|

`pageerror`

|

`ERROR`

|

### Ví dụ

Event:

JSON

```
{
  "event_type": "network_request",
  "event_id": "event-100",
  "execution_id": "exec-10",
  "payload": {
    "method": "POST",
    "url": "https://example.com/api/login",
    "body": "{\"userId\":\"u01\",\"sign\":\"abc\"}"
  }
}
```

Node:

JSON

```
{
  "node_id": "request:event-100",
  "node_type": "NETWORK_REQUEST",
  "properties": {
    "method": "POST",
    "url": "https://example.com/api/login",
    "body_hash": "sha256:...",
    "execution_id": "exec-10"
  },
  "source_event_id": "event-100"
}
```

# 6. Value Identity — thành phần quan trọng nhất

Nếu chỉ tạo node từ event, graph sẽ chưa thể hiện được data lineage.

Ví dụ:

JavaScript

```
const userId = localStorage.getItem("user_id");
const sign = generateSignature(userId);
fetch("/api/data", {
  headers: { "X-Sign": sign }
});
```

Graph cần nhận diện các giá trị:

```
"user_123"
    │
    ▼
Value: userId
    │
    ▼
generateSignature(userId)
    │
    ▼
Value: "a8c91..."
    │
    ▼
X-Sign header
```

## 6.1. Không nên nhận diện value chỉ bằng giá trị plaintext

Ví dụ cùng một chuỗi:

```
"123456"
```

có thể xuất hiện trong:

* User ID.

* Timestamp.

* Request ID.

* Giá sản phẩm.

* Một phần của token.

* Dữ liệu không liên quan.

Do đó cần xây dựng `ValueIdentity` dựa trên nhiều thuộc tính.

JSON

```
{
  "value_ref": "value:sha256:abc",
  "value_hash": "sha256:abc",
  "value_type": "string",
  "length": 6,
  "normalized_length": 6,
  "first_seen_event_id": "event-001",
  "page_id": "page-001",
  "frame_id": "frame-main",
  "scope": "session",
  "sensitivity": "unknown"
}
```

## 6.2. Các mức độ nhận diện

### Mức 1 — Exact match

Hai giá trị giống hệt nhau:

```
Value A = "user_123"
Value B = "user_123"
```

Tạo quan hệ ứng viên:

```
Value A ──SAME_VALUE_AS──> Value B
```

Độ tin cậy chỉ nên ở mức trung bình vì giống nhau không đồng nghĩa cùng nguồn gốc.

### Mức 2 — Hash match

Hai giá trị có cùng hash và cùng loại dữ liệu:

```
sha256(value_A) == sha256(value_B)
```

Phù hợp với giá trị dài hoặc đã được redaction.

### Mức 3 — Structural match

Ví dụ cùng một object:

JSON

```
{
  "userId": "u01",
  "timestamp": 123
}
```

được serialize thành:

JSON

```
{"userId":"u01","timestamp":123}
```

Có thể nhận diện quan hệ dựa trên:

* JSON path.

* Key name.

* Parent execution.

* Thời gian.

* Hash của field.

* Quan hệ serialize/deserialize.

### Mức 4 — Explicit runtime identity

Nếu instrumentation có thể truyền một `value_ref` ổn định khi giá trị được tạo và sử dụng, đây là bằng chứng mạnh hơn so với so sánh plaintext.

Tuy nhiên, cần lưu ý JavaScript primitive như string/number không giữ identity theo cách object giữ identity. Vì vậy, runtime identity phải được thiết kế như provenance metadata, không nên giả định đó là object identity thực tế.

# 7. Execution Projection

## 7.1. Gom function call, return và throw

Phase 1 có thể ghi:

```
function_call: exec-001
function_return: exec-001
```

Phase 2 cần gom chúng thành một execution duy nhất:

JSON

```
{
  "execution_id": "exec-001",
  "function_name": "generateSignature",
  "status": "RETURN",
  "started_at_ns": 1000,
  "ended_at_ns": 1500,
  "arguments_ref": [
    "value:input-01"
  ],
  "return_value_ref": "value:output-01",
  "source_event_ids": [
    "event-call-01",
    "event-return-01"
  ]
}
```

## 7.2. Các trạng thái execution

```
STARTED
RETURNED
THREW
CANCELLED
INCOMPLETE
UNKNOWN
```

`INCOMPLETE` rất quan trọng trong trường hợp:

* Trang bị đóng.

* Browser crash.

* Instrumentation bị lỗi.

* Promise chưa hoàn thành khi session dừng.

* Event return bị mất.

Không nên mặc định mọi execution không có return là lỗi.

## 7.3. Parent-child execution

Ví dụ:

JavaScript

```
async function loadData() {
  const token = await getToken();
  return fetchData(token);
}
```

Graph:

```
loadData()
    │
    ├── CALLS ──> getToken()
    │                 │
    │                 └── RETURNS ──> token
    │
    └── CALLS ──> fetchData(token)
```

Nếu instrumentation không bắt được call trực tiếp giữa hai function, chỉ tạo edge `CALLS` khi có bằng chứng như:

* `parent_execution_id`.

* Call stack.

* Runtime instrumentation.

* Correlation ID.

* Explicit event linkage.

Không nên suy luận `CALLS` chỉ vì function B xuất hiện sau function A.

# 8. Network Projection

## 8.1. Liên kết execution với request

Một request có thể được tạo bởi:

JavaScript

```
fetch(url, options);
```

hoặc:

JavaScript

```
xhr.open(...);
xhr.send(...);
```

hoặc bởi thư viện:

JavaScript

```
axios.post(...);
```

Phase 2 cần tạo quan hệ:

```
EXECUTION ──INITIATES──> NETWORK_REQUEST
```

### Các nguồn bằng chứng

|
Bằng chứng

|

Độ tin cậy

|
| --- | --- |
|

Request có `execution_id` trực tiếp

|

Cao

|
|

Runtime instrumentation ghi initiator

|

Cao

|
|

Stack trace chứa function

|

Trung bình–cao

|
|

Thời gian gần nhau

|

Thấp

|
|

URL tương tự

|

Rất thấp

|

Không nên liên kết request với function chỉ vì function đó chạy ngay trước request.

## 8.2. Network request node

JSON

```
{
  "node_id": "request:event-200",
  "node_type": "NETWORK_REQUEST",
  "properties": {
    "method": "POST",
    "host": "example.com",
    "path": "/api/data",
    "query": {},
    "headers_ref": "headers:200",
    "body_ref": "value:body-200",
    "status": "COMPLETED",
    "resource_type": "fetch",
    "initiator_type": "script"
  }
}
```

Các thông tin nhạy cảm như cookie, authorization và token nên được lưu theo chính sách redaction của Phase 1.

## 8.3. Liên kết request với response

Đây là quan hệ xác định được tương đối chắc chắn khi Playwright cung cấp request/response correlation.

```
NETWORK_REQUEST ──HAS_RESPONSE──> NETWORK_RESPONSE
```

Nếu request thất bại:

```
NETWORK_REQUEST ──FAILED_WITH──> ERROR
```

Nếu chỉ có request nhưng không có response, trạng thái nên là:

```
PENDING
FAILED
ABORTED
INCOMPLETE
UNKNOWN
```

Không được mặc định là HTTP error nếu không có HTTP response.

# 9. Storage Projection

## 9.1. Storage read

Ví dụ:

JavaScript

```
const token = localStorage.getItem("access_token");
```

Tạo:

```
STORAGE_OPERATION
    │
    └── PRODUCES ──> VALUE(token)
```

Và nếu có execution:

```
EXECUTION ──READS──> STORAGE_OPERATION
STORAGE_OPERATION ──PRODUCES──> VALUE
```

## 9.2. Storage write

JavaScript

```
localStorage.setItem("access_token", token);
```

Graph:

```
VALUE(token)
    │
    ▼
STORAGE_OPERATION(setItem)
    │
    ▼
Storage Key: access_token
```

Nên phân biệt:

* `storage_type`: local/session/cookie.

* `scope`: origin hoặc domain.

* `key`.

* `operation`: read/write/delete.

* `value_ref`.

* `sensitivity`.

* `is_redacted`.

Không nên lưu plaintext token mặc định trong graph projection.

# 10. Edge Inference — tạo quan hệ như thế nào?

Nên phân chia edge thành ba nhóm.

## 10.1. Explicit edges

Được ghi trực tiếp từ instrumentation.

Ví dụ:

```
Execution ID → Network Request ID
```

Đây là loại edge đáng tin cậy nhất.

JSON

```
{
  "edge_type": "INITIATES",
  "inferred": false,
  "confidence": 1.0
}
```

## 10.2. Structural edges

Được tạo dựa trên cấu trúc event.

Ví dụ:

* `function_call` và `function_return` có cùng `execution_id`.

* Request và response có cùng Playwright request object.

* Execution có `parent_execution_id`.

* Storage event thuộc cùng page/frame.

JSON

```
{
  "edge_type": "HAS_RESPONSE",
  "inferred": false,
  "confidence": 1.0
}
```

## 10.3. Heuristic edges

Được suy luận từ các dấu hiệu không chắc chắn:

* Giá trị giống nhau.

* Thời gian gần nhau.

* Cùng page/frame.

* Tương đồng key name.

* Cùng execution context.

* Body request chứa một giá trị từng xuất hiện trước đó.

JSON

```
{
  "edge_type": "CONSUMES",
  "inferred": true,
  "confidence": 0.62,
  "evidence": {
    "match_type": "exact_value",
    "same_page": true,
    "time_delta_ns": 2000
  }
}
```

### Quy tắc quan trọng

Không biến heuristic thành sự thật.

Nên lưu:

```
edge_type
confidence
inferred
evidence
rule_version
```

Để sau này có thể lọc:

```
Chỉ lấy edge có confidence >= 0.9
Chỉ lấy edge explicit
Chỉ lấy edge được tạo bởi rule_version = 1.2
```

# 11. Thiết kế Database cho Graph

Có thể sử dụng SQLite trong Phase 2, vì dữ liệu chủ yếu là trace theo session và cần truy vấn có điều kiện.

## 11.1. Bảng `graph_nodes`

SQL

```
CREATE TABLE graph_nodes (
    node_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    source_event_id TEXT,
    page_id TEXT,
    frame_id TEXT,
    execution_id TEXT,
    timestamp_ns INTEGER,
    properties_json TEXT NOT NULL,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

## 11.2. Bảng `graph_edges`

SQL

```
CREATE TABLE graph_edges (
    edge_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,

    confidence REAL NOT NULL,
    inferred INTEGER NOT NULL DEFAULT 0,
    rule_version TEXT,

    evidence_json TEXT,
    source_event_id TEXT,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id),

    FOREIGN KEY (source_node_id)
        REFERENCES graph_nodes(node_id),

    FOREIGN KEY (target_node_id)
        REFERENCES graph_nodes(node_id)
);
```

## 11.3. Bảng `graph_values`

Có thể tách riêng để hỗ trợ value matching:

SQL

```
CREATE TABLE graph_values (
    value_ref TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    value_type TEXT,
    length INTEGER,
    normalized_value_hash TEXT,
    sensitivity TEXT,
    redacted_value TEXT,
    first_seen_ns INTEGER,
    metadata_json TEXT
);
```

## 11.4. Bảng `graph_evidence`

Nếu evidence phức tạp hoặc có nhiều event:

SQL

```
CREATE TABLE graph_evidence (
    evidence_id TEXT PRIMARY KEY,
    edge_id TEXT NOT NULL,
    event_id TEXT,
    evidence_type TEXT NOT NULL,
    evidence_json TEXT NOT NULL,

    FOREIGN KEY (edge_id)
        REFERENCES graph_edges(edge_id)
);
```

# 12. Index bắt buộc

Nếu không có index, việc truy vấn graph trên hàng triệu event sẽ chậm.

SQL

```
CREATE INDEX idx_graph_nodes_session_type
ON graph_nodes(session_id, node_type);

CREATE INDEX idx_graph_nodes_execution
ON graph_nodes(session_id, execution_id);

CREATE INDEX idx_graph_nodes_timestamp
ON graph_nodes(session_id, timestamp_ns);

CREATE INDEX idx_graph_edges_source
ON graph_edges(session_id, source_node_id);

CREATE INDEX idx_graph_edges_target
ON graph_edges(session_id, target_node_id);

CREATE INDEX idx_graph_edges_type
ON graph_edges(session_id, edge_type);

CREATE INDEX idx_graph_values_hash
ON graph_values(session_id, value_hash);
```

# 13. Graph Projection Pipeline

## Bước 1 — Chọn session

Input:

JSON

```
{
  "session_id": "session-001",
  "projection_version": "v1",
  "rebuild": false
}
```

Kiểm tra:

* Session tồn tại.

* Event store có dữ liệu.

* Session đã dừng hoặc cho phép projection incremental.

* Projection version tương thích.

## Bước 2 — Đọc event theo thứ tự

Nên đọc theo:

SQL

```
ORDER BY timestamp_ns ASC, sequence ASC
```

Không chỉ sắp xếp theo `timestamp_ns`, vì nhiều event có thể có timestamp giống nhau.

Nếu event được gửi từ nhiều context, cần thêm:

* `sequence`.

* `page_id`.

* `frame_id`.

* `event_id`.

## Bước 3 — Normalize event

Chuẩn hóa:

* Tên event.

* Timestamp.

* Page/frame.

* Execution ID.

* URL.

* Header.

* Body.

* Value type.

* Reference tới event gốc.

Ví dụ:

```
"POST https://example.com/api?a=1"
```

thành:

JSON

```
{
  "method": "POST",
  "scheme": "https",
  "host": "example.com",
  "path": "/api",
  "query": {
    "a": "1"
  }
}
```

## Bước 4 — Tạo node

Mỗi projector xử lý một nhóm event:

Python

Chạy

```
class NodeProjector(Protocol):
    def project(self, event: EventEnvelope) -> list[GraphNode]:
        ...
```

Ví dụ:

Python

Chạy

```
class NetworkNodeProjector:
    def project(self, event):
        if event.event_type != "network_request":
            return []

        return [
            GraphNode(
                node_id=f"request:{event.event_id}",
                node_type=NodeType.NETWORK_REQUEST,
                source_event_id=event.event_id,
                properties=normalize_request(event.payload),
            )
        ]
```

## Bước 5 — Xây dựng các index tạm

Cần những index trong bộ nhớ hoặc database:

```
execution_id → execution node
event_id → node IDs
request_id → request node
response_id → response node
value_hash → value nodes
page_id/frame_id → context
storage key → latest storage operation
```

Ví dụ:

Python

Chạy

```
execution_index: dict[str, str]
request_index: dict[str, str]
event_node_index: dict[str, list[str]]
value_hash_index: dict[str, list[str]]
```

Không nên chỉ dùng dictionary trong memory nếu session quá lớn. Có thể batch và ghi index vào SQLite.

## Bước 6 — Tạo structural edges

Ví dụ:

```
Function call + function return
    → EXECUTION

Execution + parent_execution_id
    → PARENT_OF

Request + response
    → HAS_RESPONSE

Execution + explicit request initiator
    → INITIATES
```

Các edge này nên được tạo trước heuristic edge.

## Bước 7 — Tạo value observations

Mỗi giá trị được quan sát cần được chuẩn hóa:

JSON

```
{
  "value_ref": "value:001",
  "value_hash": "sha256:...",
  "value_type": "string",
  "length": 32,
  "source": "function_return",
  "sensitivity": "potential_token"
}
```

Nên hỗ trợ:

* Primitive.

* JSON object.

* JSON array.

* Buffer-like data.

* Request body.

* Response body.

* Header value.

* Storage value.

Cần giới hạn:

```
max_depth
max_string_length
max_array_items
max_object_keys
max_payload_bytes
```

Nếu vượt giới hạn:

```
TRUNCATED
```

và lưu metadata về việc bị cắt.

## Bước 8 — Tạo data-flow edges

Ví dụ rule:

```
Storage Read → Value Produced
Function Return → Value Produced
Value → Function Argument Consumed
Value → Request Header/Body Consumed
Value → Storage Write
```

Mỗi edge phải ghi:

* Rule nào tạo edge.

* Event nào làm bằng chứng.

* Exact match hay heuristic.

* Confidence.

* Khoảng cách thời gian.

* Context page/frame.

## Bước 9 — Validate graph

Kiểm tra:

* Node source có tồn tại.

* Node target có tồn tại.

* Không có edge trỏ tới node khác session.

* Không có duplicate edge không hợp lệ.

* `confidence` nằm trong `[0, 1]`.

* Timestamp hợp lệ.

* Execution return không nằm trước execution call.

* Request response không thuộc session khác.

* Edge explicit không bị ghi đè thành heuristic.

## Bước 10 — Commit theo batch

Không nên ghi từng node/edge bằng một transaction riêng.

```
Read batch
    → Project batch
    → Validate batch
    → BEGIN TRANSACTION
    → Insert nodes
    → Insert values
    → Insert edges
    → COMMIT
```

Nếu lỗi:

```
ROLLBACK
```

Nên hỗ trợ idempot
