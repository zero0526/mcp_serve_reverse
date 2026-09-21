# Phase 3: Lineage Analysis

## 1. Mục tiêu của Phase 3

Phase 2 — Graph Projection chuyển event thành graph gồm node và edge. Tuy nhiên, graph mới chỉ mô tả các quan hệ đã quan sát hoặc suy luận cục bộ.

Phase 3 — Lineage Analysis sử dụng graph để phân tích nguồn gốc, quá trình biến đổi và nơi sử dụng của dữ liệu trong browser.

Ví dụ câu hỏi cần trả lời:

* Tham số `sign` trong request được tạo từ những dữ liệu nào?

* `access_token` được đọc từ storage, cookie hay response?

* Hàm nào đã biến đổi dữ liệu trước khi gửi lên server?

* Giá trị nào ảnh hưởng trực tiếp hoặc gián tiếp đến request?

* Request có sử dụng dữ liệu từ một request trước đó không?

* Có thể xác định chính xác chuỗi biến đổi của một tham số không?

* Đâu là bằng chứng quan sát được, đâu chỉ là giả thuyết?

### Đầu vào và đầu ra

```
Phase 1: Raw Events
        │
        ▼
Phase 2: Projected Graph
        │
        ▼
Phase 3: Lineage Analysis
        │
        ├── Backward Lineage
        ├── Forward Lineage
        ├── Data Transformation Analysis
        ├── Request Dependency Analysis
        ├── Parameter Classification
        ├── Confidence Evaluation
        └── Analysis Report
```

Đầu ra không chỉ là một đồ thị mà là kết luận có cấu trúc, đường đi dữ liệu và bằng chứng đi kèm.

# 2. Phạm vi công việc

## 2.1. Các chức năng chính

|
Chức năng

|

Mô tả

|
| --- | --- |
|

Backward lineage

|

Truy ngược nguồn gốc của một giá trị

|
|

Forward lineage

|

Theo dõi giá trị được sử dụng ở đâu

|
|

Transformation analysis

|

Phân tích các bước biến đổi

|
|

Request dependency

|

Tìm dữ liệu ảnh hưởng đến request

|
|

Parameter analysis

|

Phân loại query/header/body/cookie

|
|

Correlation analysis

|

Liên kết dữ liệu giữa nhiều request

|
|

Confidence analysis

|

Đánh giá mức độ chắc chắn

|
|

Evidence report

|

Tạo báo cáo có bằng chứng

|
|

Gap detection

|

Xác định các điểm thiếu dữ liệu

|
|

Hypothesis generation

|

Tạo giả thuyết để kiểm chứng ở phase sau

|

## 2.2. Những gì chưa nên khẳng định

Lineage Analysis không thể tự động khẳng định rằng:

* Một hàm chắc chắn tạo ra chữ ký nếu chỉ thấy output giống nhau.

* Một tham số được mã hóa bằng thuật toán cụ thể khi chưa có bằng chứng.

* Một giá trị là secret chỉ vì nó có entropy cao.

* Một request phụ thuộc vào request trước chỉ vì chúng xảy ra liên tiếp.

* Một giá trị đã được giải mã nếu chỉ có hai chuỗi tương đồng.

Nên phân biệt:

```
Observed Fact
    ≠
Strongly Supported Inference
    ≠
Weak Hypothesis
```

# 3. Kiến trúc Phase 3

```
                 ┌─────────────────────┐
                 │    Graph Store      │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Lineage Resolver    │
                 └──────────┬──────────┘
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
┌────────────────┐ ┌─────────────────┐ ┌──────────────────┐
│ Path Analyzer  │ │ Transform       │ │ Dependency       │
│                │ │ Analyzer        │ │ Analyzer         │
└───────┬────────┘ └────────┬────────┘ └────────┬─────────┘
        └───────────────────┼──────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │ Confidence Engine   │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ Lineage Report      │
                 └─────────────────────┘
```

Đề xuất cấu trúc:

```
app/
  application/
    lineage/
      trace_backward.py
      trace_forward.py
      analyze_request.py
      analyze_transformation.py
      compare_values.py
      generate_report.py

  domain/
    lineage/
      lineage_path.py
      lineage_step.py
      transformation.py
      evidence.py
      hypothesis.py
      confidence.py
      analysis_result.py

  infrastructure/
    lineage/
      lineage_cache.py
      lineage_repository.py
      report_serializer.py

  adapters/
    lineage/
      graph_traversal.py
      value_matcher.py
      transformation_detector.py
      request_dependency.py
```

# 4. Các khái niệm cốt lõi

## 4.1. Data lineage

Data lineage là quá trình theo dõi một dữ liệu:

```
Nguồn
  → Đọc
  → Biến đổi
  → Truyền qua function
  → Serialize
  → Đưa vào request
```

Ví dụ:

JavaScript

```
const userId = localStorage.getItem("user_id");
const timestamp = Date.now();
const sign = generateSignature(userId, timestamp);

fetch("/api/data", {
  method: "POST",
  body: JSON.stringify({ userId, timestamp, sign })
});
```

Lineage:

```
localStorage.user_id
        │
        ▼
Value: userId
        │
        ├───────────────┐
        ▼               │
generateSignature()    │
        │               │
        ▼               │
Value: sign             │
        │               │
        └───────┐       │
                ▼       ▼
             JSON.stringify()
                    │
                    ▼
              Request Body
                    │
                    ▼
              POST /api/data
```

## 4.2. Lineage step

Mỗi bước trong đường đi dữ liệu cần có thông tin:

JSON

```
{
  "step_id": "step-001",
  "node_id": "exec:generate-signature",
  "operation": "FUNCTION_TRANSFORM",
  "input_refs": [
    "value:user-id",
    "value:timestamp"
  ],
  "output_refs": [
    "value:sign"
  ],
  "evidence_event_ids": [
    "event-101",
    "event-102"
  ],
  "confidence": 0.96,
  "status": "OBSERVED"
}
```

Các trạng thái:

```
OBSERVED
SUPPORTED_INFERENCE
HEURISTIC
UNKNOWN
MISSING_EVIDENCE
CONFLICTING
```

# 5. Backward Lineage Analysis

## 5.1. Mục tiêu

Bắt đầu từ một giá trị hoặc request và truy ngược về nguồn gốc.

Ví dụ:

```
Request Header: X-Sign
        ▲
        │
Value: sign
        ▲
        │
Execution: generateSignature()
        ▲
        │
Value: user_id
        ▲
        │
Storage: localStorage.user_id
```

Câu hỏi chính:

> “Giá trị này đến từ đâu?”

## 5.2. Thuật toán cơ bản

```
Input: target_node_id
    │
    ▼
Lấy các incoming edges
    │
    ▼
Lọc edge theo loại và confidence
    │
    ▼
Truy ngược các node cha
    │
    ▼
Phát hiện cycle
    │
    ▼
Giới hạn depth / node count
    │
    ▼
Trả về các lineage paths
```

Pseudo-code:

Python

Chạy

```
def trace_backward(
    graph,
    target_node_id,
    max_depth=10,
    min_confidence=0.8,
):
    paths = []

    def visit(node_id, path, visited):
        if len(path) >= max_depth:
            paths.append(path)
            return

        if node_id in visited:
            paths.append(path)
            return

        incoming_edges = graph.incoming_edges(
            node_id=node_id,
            min_confidence=min_confidence,
        )

        if not incoming_edges:
            paths.append(path)
            return

        for edge in incoming_edges:
            if edge.source_node_id in visited:
                continue

            visit(
                edge.source_node_id,
                path + [edge],
                visited | {node_id},
            )

    visit(target_node_id, [], set())
    return paths
```

Đây là thuật toán duyệt graph cơ bản. Trong triển khai thực tế cần bổ sung:

* Giới hạn số đường đi.

* Xử lý cycle.

* Loại bỏ đường đi trùng.

* Ưu tiên edge có confidence cao.

* Tách explicit và inferred path.

* Lưu evidence ở từng bước.

# 6. Forward Lineage Analysis

## 6.1. Mục tiêu

Bắt đầu từ một giá trị và tìm tất cả nơi giá trị đó được sử dụng.

Ví dụ:

```
localStorage.user_id
        │
        ├──> generateSignature()
        │          │
        │          └──> X-Sign header
        │
        ├──> Request body
        │
        └──> Analytics event
```

Câu hỏi chính:

> “Giá trị này ảnh hưởng đến những hoạt động nào?”

## 6.2. Use case

Forward lineage hữu ích cho:

* Tìm các request sử dụng token.

* Xác định dữ liệu storage được gửi đi đâu.

* Tìm các output của một function.

* Phân tích phạm vi ảnh hưởng của một giá trị.

* Phát hiện một value xuất hiện trong nhiều API.

Không nên coi mọi giá trị giống nhau là cùng một luồng dữ liệu. Cần phân biệt:

```
Exact observed flow
    ≠
Same plaintext value
```

# 7. Transformation Analysis

Đây là phần trung tâm của Phase 3.

## 7.1. Mục tiêu

Xác định các thao tác biến đổi dữ liệu giữa input và output.

Ví dụ:

```
user_id
   │
   ▼
String concatenation
   │
   ▼
UTF-8 encoding
   │
   ▼
Hash / Signature candidate
   │
   ▼
Base64 / Hex candidate
   │
   ▼
Request parameter
```

Tuy nhiên, cần phân biệt:

* Transformation observed: đã quan sát được thao tác.

* Transformation inferred: suy luận từ dữ liệu đầu vào/đầu ra.

* Transformation unknown: không đủ dữ liệu.

## 7.2. Các nhóm transformation

|
Nhóm

|

Ví dụ

|
| --- | --- |
|

String

|

concat, substring, replace, trim

|
|

Encoding

|

UTF-8, Base64, URL encoding

|
|

Serialization

|

JSON.stringify, form encoding

|
|

Parsing

|

JSON.parse, URL parsing

|
|

Numeric

|

cộng, nhân, timestamp

|
|

Collection

|

map, filter, join

|
|

Cryptographic candidate

|

hash, HMAC, signature

|
|

Compression

|

gzip, deflate candidate

|
|

Encryption candidate

|

ciphertext-like output

|
|

Custom function

|

function ứng dụng

|

### Lưu ý

Không nên gọi một output là `SHA256`, `AES` hoặc `HMAC` chỉ dựa trên độ dài và hình dạng chuỗi. Chỉ có thể ghi:

JSON

```
{
  "transformation_type": "CRYPTOGRAPHIC_CANDIDATE",
  "algorithm": null,
  "reason": [
    "Output length is fixed",
    "Input-output relation observed"
  ],
  "confidence": 0.35
}
```

Muốn xác định thuật toán cần có bằng chứng tốt hơn, chẳng hạn:

* Call tới API cryptographic cụ thể.

* Function source hoặc runtime event.

* Input-output samples đủ để kiểm chứng.

* Known implementation.

* Instrumentation ghi nhận thao tác.

## 7.3. Transformation record

JSON

```
{
  "transformation_id": "transform-001",
  "execution_id": "exec-001",
  "operation": "FUNCTION_CALL",
  "function_name": "generateSignature",
  "inputs": [
    "value:user_id",
    "value:timestamp"
  ],
  "outputs": [
    "value:sign"
  ],
  "observed_operations": [
    "STRING_CONCAT",
    "CUSTOM_FUNCTION"
  ],
  "algorithm": null,
  "confidence": 0.91,
  "evidence_event_ids": [
    "event-001",
    "event-002"
  ]
}
```

# 8. Phân tích input-output của function

## 8.1. Mục tiêu

Xác định quan hệ giữa arguments, return value và side effects.

Ví dụ:

JavaScript

```
function buildParams(userId, timestamp) {
  return {
    userId,
    timestamp,
    sign: generateSignature(userId, timestamp)
  };
}
```

Có thể phân tích:

```
buildParams()
    ├── consumes userId
    ├── consumes timestamp
    ├── calls generateSignature()
    └── produces params object
```

## 8.2. Những thông tin cần thu thập

* Tên function.

* Arguments.

* Return value.

* Function source location nếu có.

* Parent execution.

* Child executions.

* Side effects.

* Storage reads/writes.

* Network calls.

* Serialization calls.

* Exception.

* Thời gian thực thi.

## 8.3. Phân biệt dependency trực tiếp và gián tiếp

```
user_id ──> generateSignature() ──> sign
```

là dependency trực tiếp nếu có bằng chứng argument.

Trong khi:

```
user_id ──> function A
timestamp ──> function B
             │
             ▼
         Request C
```

không đủ để kết luận `user_id` ảnh hưởng đến Request C nếu không có edge hoặc bằng chứng trung gian.

# 9. Request Dependency Analysis

## 9.1. Mục tiêu

Tìm những dữ liệu và execution có liên quan đến một request cụ thể.

Ví dụ:

```
Request POST /api/order
    │
    ├── user_id
    ├── access_token
    ├── timestamp
    ├── sign
    └── device_context
```

Kết quả cần cho biết:

|
Tham số

|

Nguồn

|

Biến đổi

|

Mức độ

|
| --- | --- | --- | --- |
|

`user_id`

|

localStorage

|

Không rõ

|

Quan sát

|
|

`timestamp`

|

Runtime

|

Number conversion

|

Quan sát

|
|

`sign`

|

Function output

|

Custom function

|

Có bằng chứng

|
|

`access_token`

|

Cookie

|

Redacted

|

Nguồn xác định

|

## 9.2. Các bước phân tích

```
1. Xác định request node
2. Tách request components:
   - URL
   - Query
   - Headers
   - Body
   - Cookies
3. Xác định value observations
4. Truy ngược từng value
5. Gộp các lineage paths
6. Loại bỏ đường đi không đủ bằng chứng
7. Tạo dependency report
```

## 9.3. Phân loại mức độ dependency

```
DIRECT
    Request body/header chứa chính value

TRANSFORMED
    Request chứa output của function nhận value

INDIRECT
    Value ảnh hưởng đến một state được sử dụng sau đó

CANDIDATE
    Quan hệ dựa trên heuristic

UNKNOWN
    Chưa có đủ bằng chứng
```

# 10. Correlation giữa nhiều request

Một ứng dụng browser có thể sử dụng response của request A để tạo request B:

```
Request A: POST /login
        │
        ▼
Response A: session_token
        │
        ▼
Storage Write: access_token
        │
        ▼
Request B: GET /profile
```

Phase 3 cần tìm quan hệ:

```
Response A
    ──PRODUCES──> Value: session_token
    ──WRITES──> Storage: access_token
    ──INFLUENCES──> Request B
```

## Điều kiện để kết luận

Có thể kết luận mạnh hơn khi có:

* Response body chứa value.

* Storage write ghi value tương ứng.

* Request B đọc cùng storage key.

* Request B sử dụng value trong header/body.

* Có correlation hoặc execution linkage.

Nếu chỉ thấy hai request xảy ra gần nhau, chỉ nên ghi:

```
TEMPORAL_CORRELATION
```

không phải:

```
DATA_DEPENDENCY
```

# 11. Confidence Engine

## 11.1. Vì sao cần confidence?

Một lineage path có thể bao gồm cả:

```
Explicit edges
    +
Structural edges
    +
Heuristic edges
```

Nếu không phân biệt, người dùng có thể hiểu sai rằng toàn bộ path đã được xác minh.

## 11.2. Confidence theo bằng chứng

Có thể thiết kế scoring theo rule-based system.

Ví dụ:

|
Bằng chứng

|

Điểm tham khảo

|
| --- | --- |
|

Explicit runtime reference

|

1.00

|
|

Cùng execution ID

|

1.00

|
|

Request-response correlation

|

1.00

|
|

Parent execution rõ ràng

|

0.95

|
|

Exact value + cùng context

|

0.70

|
|

Hash match

|

0.75

|
|

Gần nhau về thời gian

|

0.20

|
|

Cùng tên key

|

0.15

|

Đây chỉ là điểm thiết kế ban đầu, không phải xác suất thống kê được hiệu chuẩn.

## 11.3. Confidence của cả lineage path

Không nên cộng điểm tùy ý. Một cách bảo thủ:

Cpath=min⁡(c1,c2,…,cn)C_{\text{path}} = \min(c_1,c_2,\ldots,c_n)Cpath=min(c1,c2,…,cn)

Trong đó cic_ici là confidence của từng edge.

Ví dụ:

```
Edge A: 1.00
Edge B: 0.95
Edge C: 0.70
```

Khi đó:

Cpath=0.70C_{\text{path}} = 0.70Cpath=0.70

Vì một mắt xích yếu có thể làm giảm độ tin cậy của toàn bộ kết luận.

Có thể lưu cả:

* `min_edge_confidence`.

* `average_confidence`.

* `inferred_edge_count`.

* `explicit_edge_count`.

* `evidence_completeness`.

# 12. Evidence Report

Mọi kết quả lineage nên trả về bằng chứng, không chỉ trả về danh sách node.

## Ví dụ báo cáo

JSON

```
{
  "target": {
    "type": "request_parameter",
    "request_id": "request-001",
    "location": "header.X-Sign"
  },
  "lineage_paths": [
    {
      "path_id": "path-001",
      "status": "SUPPORTED_INFERENCE",
      "confidence": 0.91,
      "steps": [
        {
          "node_id": "value:user_id",
          "operation": "STORAGE_READ",
          "evidence_event_ids": ["event-001"]
        },
        {
          "node_id": "exec:generate_signature",
          "operation": "FUNCTION_TRANSFORM",
          "evidence_event_ids": ["event-002", "event-003"]
        },
        {
          "node_id": "value:sign",
          "operation": "FUNCTION_RETURN",
          "evidence_event_ids": ["event-004"]
        },
        {
          "node_id": "request:001",
          "operation": "REQUEST_HEADER",
          "evidence_event_ids": ["event-005"]
        }
      ],
      "unknowns": [
        "Exact signature algorithm was not established"
      ]
    }
  ]
}
```

### Nguyên tắc báo cáo

Báo cáo phải trả lời được:

1. Kết luận là gì?

2. Dựa trên event nào?

3. Có bao nhiêu bước suy luận?

4. Bước nào có confidence thấp?

5. Có dữ liệu nào bị redaction?

6. Có khoảng trống quan sát nào?

7. Cần thêm capture nào để xác minh?

# 13. Phát hiện điểm thiếu trong lineage

Một đường đi dữ liệu có thể bị đứt:

```
Storage Read
    │
    ▼
Value A
    │
    ▼
UNKNOWN TRANSFORMATION
    │
    ▼
Value B
    │
    ▼
Network Request
```

Phase 3 cần đánh dấu:

JSON

```
{
  "gap_type": "MISSING_EXECUTION",
  "before_node": "value:A",
  "after_node": "value:B",
  "reason": "No observed transformation event",
  "impact": "Lineage cannot be proven",
  "recommended_action": "Capture scoped runtime execution"
}
```

Các loại gap:

|
Gap

|

Ý nghĩa

|
| --- | --- |
|

Missing event

|

Event cần thiết không được capture

|
|

Missing value

|

Payload bị giới hạn hoặc redaction

|
|

Missing execution

|

Không biết function biến đổi

|
|

Missing initiator

|

Không xác định được nguồn request

|
|

Cross-context gap

|

Dữ liệu đi qua context chưa theo dõi

|
|

Serialization gap

|

Không liên kết được object và serialized body

|
|

Timing ambiguity

|

Nhiều candidate trong cùng khoảng thời gian

|

Đây là chức năng quan trọng để hệ thống không đưa ra kết luận quá mức.

# 14. So sánh giá trị và biến đổi

## 14.1. Exact comparison

So sánh trực tiếp:

```
A == B
```

Có thể phát hiện:

* Copy nguyên giá trị.

* Giá trị xuất hiện lại.

* Header/body chứa cùng token.

Nhưng không chứng minh được nguồn gốc nếu không có liên kết execution.

## 14.2. Structural comparison

Ví dụ:

JSON

```
{
  "userId": "u01",
  "timestamp": 123,
  "sign": "abc"
}
```

và:

```
userId=u01&timestamp=123&sign=abc
```

Có thể là hai biểu diễn của cùng dữ liệu, nhưng cần ghi:

```
STRUCTURAL_SIMILARITY
```

không khẳng định chắc chắn chúng được tạo từ cùng object nếu không có bằng chứng.

## 14.3. Derived value

Một giá trị được coi là derived khi có:

* Input reference rõ ràng.

* Output reference rõ ràng.

* Execution hoặc transformation event.

* Quan hệ theo thời gian hợp lệ.

* Evidence đủ để liên kết.

Ví dụ:

```
Input A + Input B
       │
       ▼
Execution E
       │
       ▼
Output C
```

# 15. Phân tích tham số request

Phase 3 nên chuẩn hóa request thành các vị trí có thể truy vấn.

```
Request
  ├── URL
  │    ├── Path
  │    └── Query
  ├── Headers
  ├── Cookies
  ├── Body
  │    ├── JSON path
  │    ├── Form field
  │    └── Raw body
  └── Metadata
```

Mỗi parameter observation:

JSON

```
{
  "parameter_id": "param-001",
  "request_id": "request-001",
  "location": "body.sign",
  "value_ref": "value:sign",
  "encoding": "json",
  "sensitivity": "unknown",
  "lineage_status": "SUPPORTED_INFERENCE",
  "confidence": 0.91
}
```

Nên hỗ trợ các vị trí:

* `query.<key>`.

* `header.<name>`.

* `cookie.<name>`.

* `body.<json_path>`.

* `body.form.<key>`.

* `url.path_segment`.

* `url.raw`.

# 16. Lineage Graph và Analysis Graph

Không nên ghi tất cả kết quả phân tích trực tiếp vào graph gốc.

## 16.1. Graph gốc

Chứa những gì được projection từ event:

```
Observed Nodes
Observed Edges
Structural Edges
```

## 16.2. Analysis graph

Chứa kết quả phân tích:

```
Lineage Paths
Transformation Candidates
Dependency Findings
Hypotheses
Confidence Scores
Evidence Summaries
```

Lý do tách biệt:

* Có thể chạy lại analysis với thuật toán mới.

* Không làm thay đổi dữ liệu capture.

* Có thể so sánh nhiều phiên bản rule.

* Tránh biến kết luận suy luận thành dữ liệu quan sát.

* Dễ audit và debug.

# 17. Database cho Phase 3

## 17.1. Bảng `lineage_analyses`

SQL

```
CREATE TABLE lineage_analyses (
    analysis_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    target_node_id TEXT,
    algorithm_version TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at_ns INTEGER,
    completed_at_ns INTEGER,
    summary_json TEXT,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

## 17.2. Bảng `lineage_paths`

SQL

```
CREATE TABLE lineage_paths (
    path_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_node_id TEXT,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    depth INTEGER NOT NULL,
    step_count INTEGER NOT NULL,
    path_json TEXT NOT NULL,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (analysis_id)
        REFERENCES lineage_analyses(analysis_id)
);
```

## 17.3. Bảng `lineage_findings`

SQL

```
CREATE TABLE lineage_findings (
    finding_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    subject_node_id TEXT,
    description TEXT NOT NULL,
    evidence_json TEXT,
    recommendation TEXT,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (analysis_id)
        REFERENCES lineage_analyses(analysis_id)
);
```

## 17.4. Bảng `transformations`

SQL

```
CREATE TABLE transformations (
    transformation_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    execution_id TEXT,
    transformation_type TEXT NOT NULL,
    function_name TEXT,
    input_refs_json TEXT,
    output_refs_json TEXT,
    algorithm TEXT,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_json TEXT,
    created_at_ns INTEGER NOT NULL,

    FOREIGN KEY (analysis_id)
        REFERENCES lineage_analyses(analysis_id)
);
```

# 18. MCP Tools cho Phase 3

## 18.1. `trace_value_lineage`

Truy nguồn gốc của một value.

JSON

```
{
  "session_id": "session-001",
  "value_ref": "value:sign",
  "direction": "backward",
  "max_depth": 10,
  "min_confidence": 0.8,
  "include_heuristics": false
}
```

Response nên bao gồm:

JSON

```
{
  "status": "COMPLETED",
  "paths_found": 2,
  "best_path_confidence": 0.91,
  "paths": [],
  "gaps": []
}
```

## 18.2. `analyze_request_lineage`

JSON

```
{
  "session_id": "session-001",
  "request_id": "request-001",
  "include_query": true,
  "include_headers": true,
  "include_body": true,
  "include_storage": true,
  "min_confidence": 0.8
}
```

Output:

```
Request
  ├── Parameter
  ├── Source values
  ├── Transformations
  ├── Storage dependencies
  ├── Execution dependencies
  └── Confidence and evidence
```

## 18.3. `analyze_transformation`

JSON

```
{
  "session_id": "session-001",
  "execution_id": "exec-001",
  "include_inputs": true,
  "include_outputs": true,
  "include_nested_executions": true
}
```

Kết quả cần phân biệt:

```
Observed operation
Candidate transformation
Unknown operation
```

## 18.4. `trace_request_dependencies`

JSON

```
{
  "session_id": "session-001",
  "request_id": "request-001",
  "direction": "backward",
  "max_depth": 12,
  "include_cross_request": true,
  "min_confidence": 0.85
}
```

## 18.5. `find_value_usages`

JSON

```
{
  "session_id": "session-001",
  "value_ref": "value:access-token",
  "direction": "forward",
  "include_redacted_matches": true,
  "limit": 100
}
```

## 18.6. `get_lineage_report`

JSON

```
{
  "analysis_id": "analysis-001",
  "format": "structured",
  "include_evidence": true,
  "include_gaps": true,
  "include_hypotheses": true
}
```

# 19. Quy trình thực thi đầy đủ

```
1. Nhận session_id và target
        │
        ▼
2. Kiểm tra graph projection version
        │
        ▼
3. Resolve target node hoặc parameter
        │
        ▼
4. Xác định các edge được phép sử dụng
        │
        ▼
5. Traverse graph
        │
        ▼
6. Xây dựng lineage paths
        │
        ▼
7. Nhận diện transformations
        │
        ▼
8. Tìm gaps và conflicting evidence
        │
        ▼
9. Tính confidence
        │
        ▼
10. Deduplicate paths
        │
        ▼
11. Tạo findings và report
        │
        ▼
12. Lưu analysis result
```

## 19.1. Idempotency

Một analysis phải có thể chạy lại mà không tạo bản ghi trùng.

Khóa logic:

```
session_id
target_node_id
analysis_type
algorithm_version
analysis_config_hash
```

Nếu thay đổi rule hoặc confidence threshold, có thể tạo analysis version mới.

# 20. Đánh giá chất lượng Phase 3

## 20.1. Ground-truth dataset

Nên xây dựng các trang web kiểm thử đơn giản với lineage đã biết.

Ví dụ:

JavaScript

```
const raw = localStorage.getItem("user_id");
const encoded = btoa(raw);
const body = JSON.stringify({ id: encoded });

fetch("/api/test", {
  method: "POST",
  body
});
```

Ground truth:

```
localStorage.user_id
    → btoa()
    → JSON.stringify()
    → request.body.id
```

Test thêm:

* Chuỗi nhiều bước.

* Nested function.

* Promise.

* Request song song.

* Storage write rồi read.

* Giá trị trùng nhưng khác nguồn.

* Dữ liệu bị redaction.

* Iframe.

* Function không được instrumentation.

## 20.2. Chỉ số đánh giá

### Lineage precision

Trong các quan hệ mà hệ thống kết luận, có bao nhiêu quan hệ đúng?

Precision=TPTP+FPPrecision = \frac{TP}{TP + FP}Precision=TP+FPTP

### Lineage recall

Trong các quan hệ thực sự tồn tại, hệ thống phát hiện được bao nhiêu?

Recall=TPTP+FNRecall = \frac{TP}{TP + FN}Recall=TP+FNTP

### Path accuracy

Tỷ lệ path được trả về có đúng thứ tự và đúng các bước.

### Evidence completeness

Tỷ lệ finding có đầy đủ:

* Source event.

* Source node.

* Edge type.

* Transformation evidence.

* Confidence explanation.

### Gap detection rate

Tỷ lệ các trường hợp thiếu bằng chứng được đánh dấu thay vì tạo kết luận sai.

# 21. Các test case quan trọng

## A. Backward lineage

* Truy ngược từ request header về function return.

* Truy ngược từ body field về storage.

* Truy ngược nhiều bước.

* Xử lý cycle.

* Giới hạn depth.

* Không theo heuristic khi `include_heuristics=false`.

## B. Forward lineage

* Tìm mọi nơi sử dụng value.

* Phân biệt exact value và value reference.

* Xử lý value bị redaction.

* Tìm usage qua serialization.

* Tìm usage qua nhiều request.

## C. Transformation

* String concat.

* Base64 hoặc encoding candidate.

* JSON serialization.

* Nested functions.

* Unknown transformation.

* Không gán thuật toán crypto khi chưa đủ bằng chứng.

## D. Reliability

* Graph có orphan node.

* Event bị mất.

* Execution không có return.

* Request không có initiator.

* Hai giá trị giống nhau nhưng khác nguồn.

* Re-run analysis không duplicate.

* Phiên bản rule khác nhau tạo kết quả riêng.

# 22. Definition of Done

Phase 3 được xem là đạt khi:

## A. Lineage engine

* Truy ngược được nguồn gốc của value.

* Theo dõi được nơi sử dụng của value.

* Hỗ trợ request parameter lineage.

* Hỗ trợ storage → function → request.

* Hỗ trợ lineage qua serialization.

* Xử lý được nhiều đường đi và cycle.

## B. Transformation analysis

* Nhận diện được execution input/output.

* Ghi nhận transformation quan sát được.

* Phân biệt transformation candidate và transformation đã xác minh.

* Không khẳng định thuật toán khi chỉ dựa trên pattern output.

* Có thể lưu unknown transformation.

## C. Confidence và evidence

* Mỗi path có confidence.

* Có thể lọc theo confidence.

* Có evidence cho từng bước.

* Phân biệt observed và inferred.

* Phát hiện missing evidence.

* Không lộ dữ liệu nhạy cảm trong report mặc định.

## D. Analysis result

* Có backward lineage.

* Có forward lineage.

* Có request dependency report.

* Có transformation report.

* Có gap report.

* Có version của thuật toán phân tích.

* Có thể chạy lại analysis.

## E. Kiểm thử

* Ground-truth dataset.

* Precision/recall cho edge suy luận.

* Path accuracy.

* Evidence completeness.

* Test event thiếu.

* Test dữ liệu trùng.

* Test asynchronous flow.

* Test redaction.

# 23. Thứ tự triển khai khuyến nghị

|
Milestone

|

Nội dung

|

Kết quả

|
| --- | --- | --- |
|

3.1

|

Lineage domain model

|

Path, step, evidence

|
|

3.2

|

Graph traversal

|

Backward/forward traversal

|
|

3.3

|

Explicit lineage

|

Chỉ sử dụng edge có bằng chứng

|
|

3.4

|

Storage lineage

|

Storage → value → execution

|
|

3.5

|

Request parameter lineage

|

Header/query/body lineage

|
|

3.6

|

Transformation analysis

|

Input/output function

|
|

3.7

|

Cross-request correlation

|

Response → storage → request

|
|

3.8

|

Confidence engine

|

Confidence theo edge/path

|
|

3.9

|

Gap detection

|

Missing evidence

|
|

3.10

|

Report generation

|

Structured lineage report

|
|

3.11

|

MCP tools

|

Truy vấn qua MCP

|
|

3.12

|

Ground-truth evaluation

|

Đánh giá độ chính xác

|

# 24. Ví dụ đầu ra cuối cùng

Với request:

```
POST /api/data
Header: X-Sign = <REDACTED>
```

Hệ thống có thể trả về:

```
Finding: Request parameter lineage

Target:
  request.header.X-Sign

Source:
  localStorage.user_id

Observed steps:
  1. Storage read: user_id
  2. Function call: generateSignature
  3. Function return: redacted signature
  4. Request header assignment

Confidence:
  0.91

Status:
  SUPPORTED_INFERENCE

Verified:
  - user_id was read from localStorage
  - generateSignature execution was observed
  - returned value was associated with X-Sign

Unknown:
  - Exact signature algorithm
  - Whether additional hidden state was used

Evidence:
  event-001, event-002, event-003, event-004
```

Điểm quan trọng là hệ thống không cần đoán thuật toán chữ ký để vẫn cung cấp lineage hữu ích.

# 25. Phân biệt Phase 2 và Phase 3

|
Nội dung

|

Phase 2: Graph Projection

|

Phase 3: Lineage Analysis

|
| --- | --- | --- |
|

Mục tiêu

|

Tạo graph

|

Phân tích graph

|
|

Đầu vào

|

Raw events

|

Graph nodes/edges

|
|

Đầu ra

|

Graph

|

Paths, findings, reports

|
|

Trọng tâm

|

Node và edge

|

Nguồn gốc và dependency

|
|

Function

|

Gom execution

|

Phân tích input/output

|
|

Value

|

Tạo value node

|

Truy vết value

|
|

Request

|

Liên kết request/response

|

Phân tích parameter dependency

|
|

Heuristic

|

Tạo candidate edge

|

Đánh giá và kết hợp candidate

|
|

Confidence

|

Gắn cho edge

|

Tính cho path/finding

|
|

Evidence

|

Lưu evidence

|

Giải thích kết luận

|
|

Kết quả

|

Quan hệ dữ liệu

|

Ý nghĩa của quan hệ dữ liệu

|

## Kết luận

Phase 3 là lớp phân tích giúp chuyển graph thành hiểu biết có thể sử dụng.

Trình tự chính:

```
Graph
  → Traverse
  → Resolve lineage
  → Analyze transformations
  → Identify dependencies
  → Evaluate confidence
  → Detect gaps
  → Generate evidence-based report
```

Điều kiện quan trọng nhất để Phase 3 đạt là:

> Với một request hoặc tham số cụ thể, hệ thống có thể truy ra nguồn dữ liệu, liệt kê các bước biến đổi, chỉ rõ bằng chứng của từng bước, phân biệt phần đã quan sát với phần suy luận, và không đưa ra kết luận chắc chắn khi dữ liệu capture chưa đủ.

---

# 10. Báo Cáo Hoàn Thành Triển Khai Thực Tế & Hợp Đồng Bàn Giao (Handover)

## 10.1. Chuyển giao từ Phase 1 (Event Store & Multi-Session Capture)

Giai đoạn 1 đã bàn giao trọn vẹn hạ tầng thu thập và lưu trữ sự kiện:
- **Stealth Engine:** Sử dụng CloakHQ/cloakbrowser với cơ chế queue-draining bất đồng bộ, chống drop event khi browser đóng nhanh.
- **Relational Event Store (SQLite):**
  - `sessions`: Lưu thông tin session kèm `metadata_json` chứa `task_id` phục vụ gom nhóm multi-session.
  - `trace_events`: Ghi nhận toàn bộ thao tác người dùng, script execution, network hooks.
  - `network_requests` & `network_responses`: Bóc tách đầy đủ method, url, query_json, headers_json, body_json, status, content_type.
  - `storage_operations`: Ghi nhận chi tiết các thao tác `setItem`, `getItem`, `removeItem`, `cookie_change`.
- **Pre-seed State Support:** Cho phép inject token/cookie vào storage trước khi chạy task để bỏ qua các bước xác thực dư thừa.

## 10.2. Kiến Trúc Hoàn Thiện của Phase 2 (Clean Architecture & DRY)

Phase 2 được thiết kế chặt chẽ theo mô hình Clean Architecture, tuân thủ nguyên tắc Single Responsibility và DRY:

```
┌────────────────────────────────────────────────────────────────────────┐
│                              Domain Layer                              │
│  - nodes.py: NodeType, GraphNode                                       │
│  - relations.py: RelationType (READS_FROM, USED_IN, STORES_IN...)      │
│  - edges.py: EdgeEvidence, GraphEdge                                   │
│  - entities.py: ParameterType, LineageStep, LineagePath, ReplaySpec     │
│  - differential.py: FieldVariance, SessionComparisonResult             │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│                               Ports Layer                              │
│  - graph_repository.py: GraphRepositoryPort                            │
│  - analysis.py: LineageServicePort                                     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│                           Application Layer                            │
│  - ProjectSessionGraphUseCase: Chiếu sự kiện thành Property Graph      │
│  - TraceLineageUseCase: Thuật toán BFS/DFS backward & forward lineage   │
│  - DifferentialAnalysisUseCase: Phân tích vi phân đa phiên theo task    │
│  - GenerateReplaySpecUseCase: Đóng gói ReplaySpec cho Phase 3          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│                             Adapters Layer                             │
│  - SQLiteGraphRepository: Lưu trữ graph_nodes, graph_edges, evidence   │
│  - GraphProjector: Thuật toán phân rã JSON leaves và suy luận cạnh     │
└────────────────────────────────────────────────────────────────────────┘
```

### Các tính năng cốt lõi đã hoàn thành:
1. **Deterministic Graph Projection (`GraphProjector`):**
   - Đảm bảo tính toàn vẹn khóa chính đa phiên: ID node luôn mang tiền tố `session_id` (`node_stor_{session_id}_...`, `node_req_{session_id}_...`).
   - Tự động bóc tách lá (leaves flattening) cho JSON body, Headers, Query parameters.
   - Tạo các quan hệ ngữ nghĩa `CONTAINS`, `READS_FROM`, `USED_IN`, `STORES_IN`, `ASSOCIATED_WITH`.
2. **Lineage Traversal (`TraceLineageUseCase`):**
   - **Backward Lineage:** Truy ngược từ Sink (tham số request) về Origin (localStorage, cookie, response trước hoặc user input).
   - **Forward Lineage:** Lần theo dòng dữ liệu từ Origin đến các điểm Sink chịu ảnh hưởng.
   - Đi kèm bằng chứng (`EdgeEvidence`) và độ tin cậy (`confidence` >= 0.9 đối với token/storage match).
3. **Differential Variance Analysis (`DifferentialAnalysisUseCase`):**
   - Phân tích so sánh vi phân giữa các phiên cùng thực hiện một `task_id`.
   - Tự động phân loại chính xác các trường:
     - `CONSTANT`: Các header/trường tĩnh, kể cả auto-computed transport headers (`content-length`).
     - `SESSION_TOKEN`: Token ủy quyền, cookie phiên, bearer token.
     - `TIMESTAMP`: Giá trị thời gian epoch millisecond / ISO.
     - `EPHEMERAL_NONCE`: Nonce động theo từng request.
     - `USER_INPUT`: Các biến động do người dùng nhập vào payload qua các phiên.

## 10.3. Hợp Đồng Bàn Giao Sang Phase 3 (Replay & Code Synthesis Contract)

Để chuyển giao sang Phase 3 (xây dựng Replay Engine và trình sinh mã tự động - Code Synthesis), Phase 2 xuất ra cấu trúc chuẩn hóa `ReplaySpec`:

```json
{
  "task_id": "task_example_123",
  "target_request_id": "req_post_order_abc",
  "method": "POST",
  "url_template": "https://api.example.com/v1/orders",
  "headers_template": {
    "Content-Type": "application/json",
    "Authorization": "Bearer {{auth_token}}"
  },
  "body_template": {
    "name": "{{name}}",
    "timestamp": "{{timestamp}}"
  },
  "required_variables": [
    "name",
    "timestamp"
  ],
  "session_prerequisites": [
    {
      "order": 1,
      "step_type": "read_storage",
      "target_id": "node_stor_sess_local_storage_auth_token",
      "action": "localStorage.getItem('auth_token')",
      "output_bindings": {
        "auth_token": "auth_token"
      }
    }
  ],
  "parameter_lineages": {
    "request": {
      "target_node_id": "node_req_sess_req_post_order_abc",
      "target_param": "auth_token",
      "origin_node_id": "node_stor_sess_local_storage_auth_token",
      "origin_type": "storage",
      "origin_key": "auth_token",
      "overall_confidence": 0.95,
      "status": "CONFIRMED"
    }
  },
  "metadata": {
    "session_count": 2,
    "summary": {
      "total_fields": 5,
      "constants_count": 3,
      "tokens_count": 1,
      "variables_count": 1
    }
  }
}
```

### Hướng dẫn tiêu thụ cho Phase 3:
- **Replay Engine:**
  1. Kiểm tra `session_prerequisites`: Chạy trước các bước chuẩn bị (đọc storage, lấy token, pre-seed cookies).
  2. Binds các `required_variables`: Điền giá trị mới cho người dùng nhập hoặc sinh `timestamp` / `nonce`.
  3. Replay HTTP Request bằng `httpx` hoặc `curl` độc lập với browser.
- **Code Synthesizer:**
  1. Render script Python hoàn chỉnh (sử dụng `httpx` hoặc `requests`) từ `ReplaySpec`.
  2. Tạo function parameters tương ứng với `required_variables`.
  3. Thiết lập headers & cookies tự động hóa.

