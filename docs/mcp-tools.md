# Thiết kế chi tiết MCP Tools cho `api_lineage`

Với cấu trúc hiện tại, MCP nên đóng vai trò lớp giao tiếp cho LLM/agent, không trực tiếp xử lý logic nghiệp vụ hoặc truy vấn SQL. Mỗi MCP tool nên gọi một application use case tương ứng trong `app/application`.

Kiến trúc đề xuất:

```
MCP Client / LLM
       │
       ▼
interfaces/mcp/tools/*.py
       │
       ▼
application use cases
       │
       ▼
domain + ports
       │
       ▼
SQLite / Browser / Android / Replay
```

Nên chia MCP tools thành 6 nhóm chính:

|
Nhóm

|

Mục đích

|
| --- | --- |
|

Capture

|

Bắt đầu, dừng và kiểm tra phiên capture

|
|

Trace

|

Tra cứu execution, event và timeline

|
|

Lineage

|

Truy vết nguồn gốc và luồng biến đổi dữ liệu

|
|

Network

|

Phân tích HTTP request/response

|
|

Replay

|

Chuẩn bị, thực thi và kiểm tra replay

|
|

Graph/Analysis

|

So sánh, tổng hợp và phân tích nâng cao

|

# 1. Quy ước chung cho MCP Tools

## 1.1. Quy tắc input

Mọi tool nên nhận các identifier rõ ràng:

JSON

```
{
  "session_id": "sess_01",
  "request_id": "req_01",
  "node_id": "node_01"
}
```

Không nên cho LLM truyền SQL trực tiếp:

JSON

```
{
  "sql": "SELECT * FROM ..."
}
```

Lý do:

* Kiểm soát quyền truy cập tốt hơn.

* Tránh SQL injection.

* Dễ thay đổi SQLite sang PostgreSQL hoặc Neo4j.

* Schema input/output ổn định.

* Có thể giới hạn dữ liệu nhạy cảm.

## 1.2. Các trường dùng chung

Có thể định nghĩa trong `interfaces/mcp/schemas/requests.py`:

Python

Chạy

```
from pydantic import BaseModel, Field
from typing import Literal


class SessionScope(BaseModel):
    session_id: str = Field(
        description="ID của phiên capture cần truy vấn"
    )


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class TimeRange(BaseModel):
    start_ns: int | None = None
    end_ns: int | None = None
```

Mỗi response nên có metadata:

JSON

```
{
  "session_id": "sess_01",
  "result": {},
  "metadata": {
    "truncated": false,
    "count": 10,
    "generated_at": "2026-09-20T12:00:00Z"
  },
  "warnings": []
}
```

`warnings` rất quan trọng khi:

* Dữ liệu bị redacted.

* Graph chỉ có quan hệ suy luận.

* Response bị cắt vì quá lớn.

* Capture không đầy đủ.

* Không xác định được chính xác nguồn dữ liệu.

# 2. Capture Tools

File:

```
interfaces/mcp/tools/capture.py
```

Các use case đã có:

```
application/capture/start_session.py
application/capture/stop_session.py
application/capture/capture_status.py
```

## 2.1. `start_capture_session`

### Mục đích

Khởi tạo một phiên thu thập dữ liệu từ:

* Browser + Playwright.

* Android + Frida.

* Có thể mở rộng sang các nguồn khác.

### Input

JSON

```
{
  "source": "browser",
  "name": "youtube_login_analysis",
  "target": "https://youtube.com",
  "capture_options": {
    "network": true,
    "runtime": true,
    "storage": true,
    "crypto": false,
    "screenshots": false
  },
  "metadata": {
    "environment": "ubuntu",
    "purpose": "api_analysis"
  }
}
```

Schema:

Python

Chạy

```
class StartCaptureRequest(BaseModel):
    source: Literal["browser", "android"]
    name: str
    target: str | None = None

    capture_options: dict[str, bool] = Field(
        default_factory=lambda: {
            "network": True,
            "runtime": True,
            "storage": True,
            "crypto": False,
            "screenshots": False,
        }
    )

    metadata: dict = Field(default_factory=dict)
```

### Output

JSON

```
{
  "session_id": "sess_01",
  "status": "starting",
  "source": "browser",
  "target": "https://youtube.com",
  "started_at_ns": 1726830000000000000
}
```

### Quy tắc

Tool không nên tự động tuyên bố browser đã sẵn sàng nếu adapter chưa xác nhận.

Các trạng thái:

```
created
starting
running
stopping
stopped
failed
```

## 2.2. `stop_capture_session`

### Mục đích

Dừng một session đang capture và flush các event còn trong memory.

### Input

JSON

```
{
  "session_id": "sess_01",
  "flush_pending_events": true,
  "save_screenshots": false
}
```

### Output

JSON

```
{
  "session_id": "sess_01",
  "status": "stopped",
  "started_at_ns": 1726830000000000000,
  "ended_at_ns": 1726830060000000000,
  "statistics": {
    "total_events": 1240,
    "network_requests": 86,
    "function_executions": 340,
    "storage_operations": 21,
    "crypto_operations": 0
  }
}
```

### Xử lý

```
stop adapter
    ↓
flush event buffer
    ↓
persist raw events
    ↓
normalize pending events
    ↓
project graph
    ↓
update session status
```

Không nhất thiết phải rebuild toàn bộ graph khi dừng session. Chỉ nên project những event chưa xử lý.

## 2.3. `get_capture_status`

### Mục đích

Kiểm tra trạng thái của session hoặc tất cả session đang chạy.

### Input

JSON

```
{
  "session_id": "sess_01",
  "include_statistics": true
}
```

### Output

JSON

```
{
  "session_id": "sess_01",
  "status": "running",
  "source": "browser",
  "runtime": {
    "adapter_connected": true,
    "last_event_at_ns": 1726830050000000000,
    "event_rate_per_second": 12.4
  },
  "statistics": {
    "events": 1240,
    "requests": 86,
    "errors": 2
  }
}
```

### Các cảnh báo nên phát hiện

* Adapter bị mất kết nối.

* Không có event mới trong một khoảng thời gian.

* Event queue bị đầy.

* Không thể ghi SQLite.

* Có lỗi parse payload.

* Có event bị loại bỏ.

# 3. Trace Tools

File:

```
interfaces/mcp/tools/trace.py
```

Tương ứng:

```
application/trace/get_execution_context.py
application/trace/get_timeline.py
application/trace/search_events.py
```

Trace tập trung vào sự kiện quan sát được, chưa kết luận quan hệ dữ liệu nếu chưa có bằng chứng.

## 3.1. `search_trace_events`

### Mục đích

Tìm các event theo keyword, loại event, function, URL hoặc khoảng thời gian.

### Input

JSON

```
{
  "session_id": "sess_01",
  "query": "authorization",
  "event_types": [
    "function_call",
    "network_request",
    "storage_read"
  ],
  "function_name": null,
  "url_contains": null,
  "start_ns": null,
  "end_ns": null,
  "limit": 50,
  "offset": 0
}
```

### Các trường tìm kiếm

|
Trường

|

Ví dụ

|
| --- | --- |
|

`query`

|

`authorization`, `token`, `userId`

|
|

`event_types`

|

`network_request`, `function_call`

|
|

`function_name`

|

`generateSignature`

|
|

`url_contains`

|

`/api/v1`

|
|

`value_hash`

|

SHA-256 hash

|
|

`time_range`

|

Khoảng timestamp

|

### Output

JSON

```
{
  "session_id": "sess_01",
  "events": [
    {
      "event_id": "evt_100",
      "event_type": "function_call",
      "timestamp_ns": 1726830010000000000,
      "function_name": "buildHeaders",
      "execution_id": "exec_10",
      "summary": "Function called with 3 arguments",
      "matched_fields": [
        "function_name",
        "arguments"
      ]
    }
  ],
  "metadata": {
    "count": 1,
    "truncated": false
  }
}
```

Không nên trả toàn bộ `payload_json` mặc định vì có thể rất lớn hoặc chứa secret. Cung cấp `detail_level`:

```
summary
normal
full
```

## 3.2. `get_execution_context`

### Mục đích

Lấy context của một lần thực thi function:

* Function nào được gọi.

* Parent execution.

* Arguments.

* Return value.

* Stack trace.

* Các network request liên quan.

* Các event trước và sau.

### Input

JSON

```
{
  "session_id": "sess_01",
  "execution_id": "exec_10",
  "include_arguments": true,
  "include_return_value": true,
  "include_stack_trace": true,
  "include_related_network": true,
  "max_related_events": 30
}
```

### Output

JSON

```
{
  "execution": {
    "execution_id": "exec_10",
    "function_name": "buildHeaders",
    "module_name": "app.js",
    "source_location": {
      "file": "app.js",
      "line": 142,
      "column": 8
    },
    "parent_execution_id": "exec_09",
    "started_at_ns": 1000,
    "ended_at_ns": 2000,
    "status": "completed"
  },
  "arguments": [
    {
      "index": 0,
      "type": "string",
      "value_ref": "val_01",
      "redacted": true
    }
  ],
  "return_value": {
    "value_ref": "val_02",
    "type": "object"
  },
  "related_events": [
    {
      "event_id": "evt_101",
      "event_type": "network_request"
    }
  ]
}
```

### Lưu ý

`include_arguments` và `include_return_value` nên chịu chính sách redaction. Không trả plaintext của:

* Cookie.

* Authorization token.

* Password.

* Private key.

* Session token.

## 3.3. `get_trace_timeline`

### Mục đích

Hiển thị chuỗi hoạt động theo thời gian để hiểu request được tạo ra như thế nào.

### Input

JSON

```
{
  "session_id": "sess_01",
  "start_ns": 1000000,
  "end_ns": 3000000,
  "focus_execution_id": "exec_10",
  "event_types": [
    "function_call",
    "function_return",
    "network_request",
    "network_response",
    "storage_read",
    "storage_write"
  ],
  "limit": 100
}
```

### Output

JSON

```
{
  "timeline": [
    {
      "sequence": 1,
      "timestamp_ns": 1000100,
      "event_id": "evt_01",
      "type": "storage_read",
      "summary": "Read localStorage key: auth_token",
      "execution_id": "exec_01"
    },
    {
      "sequence": 2,
      "timestamp_ns": 1000200,
      "event_id": "evt_02",
      "type": "function_call",
      "summary": "Call buildAuthorizationHeader",
      "execution_id": "exec_10"
    },
    {
      "sequence": 3,
      "timestamp_ns": 1000300,
      "event_id": "evt_03",
      "type": "network_request",
      "summary": "POST /api/v1/data",
      "execution_id": "exec_10"
    }
  ]
}
```

Timeline nên hỗ trợ hai chế độ:

```
temporal:
    sắp xếp theo timestamp

causal:
    ưu tiên quan hệ parent-child và dependency
```

Không nên coi timestamp là bằng chứng chắc chắn về quan hệ dữ liệu.

# 4. Lineage Tools

File:

```
interfaces/mcp/tools/lineage.py
```

Đây là nhóm quan trọng nhất của hệ thống.

Các use case:

```
trace_origin.py
trace_downstream.py
explain_path.py
find_transformations.py
compare_lineage.py
```

Nên phân biệt rõ:

```
observed lineage
inferred lineage
unknown lineage
```

LLM phải biết quan hệ nào được quan sát trực tiếp và quan hệ nào chỉ được suy luận.

## 4.1. `trace_origin`

### Mục đích

Truy tìm nguồn gốc của một giá trị hoặc trường dữ liệu.

Ví dụ:

```
Authorization header
    ← generated token
    ← localStorage.auth_token
    ← login response
```

### Input

Có thể hỗ trợ nhiều dạng target:

JSON

```
{
  "session_id": "sess_01",
  "target": {
    "type": "request_field",
    "request_id": "req_20",
    "field_path": "headers.Authorization"
  },
  "direction": "upstream",
  "max_depth": 8,
  "include_evidence": true,
  "include_values": false,
  "relation_types": [
    "DERIVED_FROM",
    "CONSUMES",
    "RETURNS",
    "READS_FROM"
  ]
}
```

Các target type:

```
value
variable
request_field
response_field
storage_entry
function_return
graph_node
```

### Output

JSON

```
{
  "target": {
    "type": "request_field",
    "request_id": "req_20",
    "field_path": "headers.Authorization"
  },
  "paths": [
    {
      "path_id": "path_01",
      "confidence": 0.96,
      "status": "partially_observed",
      "nodes": [
        {
          "node_id": "node_20",
          "type": "http_header",
          "label": "Authorization"
        },
        {
          "node_id": "node_15",
          "type": "function_execution",
          "label": "buildHeaders"
        },
        {
          "node_id": "node_10",
          "type": "storage_entry",
          "label": "localStorage.auth_token"
        }
      ],
      "edges": [
        {
          "relation": "PRODUCES",
          "status": "observed",
          "confidence": 1.0
        },
        {
          "relation": "READS_FROM",
          "status": "observed",
          "confidence": 0.98
        }
      ]
    }
  ],
  "warnings": [
    "Intermediate transformation was not captured"
  ]
}
```

### Quy tắc truy vấn

Không chỉ tìm theo `value_hash`. Cần kết hợp:

1. Node ID.

2. Value hash.

3. Function execution.

4. Temporal proximity.

5. Argument/return references.

6. Request field mapping.

7. Evidence score.

## 4.2. `trace_downstream`

### Mục đích

Tìm những nơi sử dụng một giá trị sau khi nó được tạo ra.

Ví dụ:

```
response.data.user_id
    ├── stored in localStorage
    ├── passed to buildRequest
    ├── inserted into query parameter
    └── sent in next API request
```

### Input

JSON

```
{
  "session_id": "sess_01",
  "source": {
    "type": "response_field",
    "response_id": "resp_10",
    "field_path": "body.user.id"
  },
  "max_depth": 6,
  "max_paths": 20,
  "include_inferred": true,
  "min_confidence": 0.6
}
```

### Output

JSON

```
{
  "source": {
    "node_id": "node_resp_user_id",
    "label": "response.body.user.id"
  },
  "downstream": [
    {
      "target_node_id": "node_storage_user_id",
      "relation": "STORES_IN",
      "confidence": 0.99,
      "evidence": [
        {
          "type": "direct_observation",
          "event_id": "evt_30"
        }
      ]
    },
    {
      "target_node_id": "node_request_user_id",
      "relation": "USED_IN",
      "confidence": 0.82,
      "evidence": [
        {
          "type": "value_hash_match",
          "event_id": "evt_40"
        }
      ]
    }
  ]
}
```

`include_inferred` nên mặc định là `false` trong truy vấn chính xác và `true` trong chế độ khám phá.

## 4.3. `explain_lineage_path`

### Mục đích

Giải thích từng bước trong một path thay vì chỉ trả graph node/edge.

Đây là tool phù hợp để LLM tạo báo cáo dễ đọc.

### Input

JSON

```
{
  "session_id": "sess_01",
  "path_id": "path_01",
  "detail_level": "detailed",
  "include_code_context": true,
  "include_evidence": true
}
```

### Output

JSON

```
{
  "path_id": "path_01",
  "summary": "Authorization header is derived from a token read from localStorage.",
  "steps": [
    {
      "step": 1,
      "from": "localStorage.auth_token",
      "to": "buildHeaders",
      "operation": "READ",
      "explanation": "Function execution read the storage entry.",
      "evidence": [
        "evt_10",
        "exec_01"
      ],
      "confidence": 0.99
    },
    {
      "step": 2,
      "from": "buildHeaders",
      "to": "headers.Authorization",
      "operation": "PRODUCE",
      "explanation": "The returned object was used as request headers.",
      "evidence": [
        "evt_12",
        "req_20"
      ],
      "confidence": 0.91
    }
  ],
  "limitations": [
    "The internal token transformation was not observed."
  ]
}
```

Tool này nên trả giải thích có cấu trúc, không yêu cầu LLM phải tự đọc toàn bộ raw event.

## 4.4. `find_transformations`

### Mục đích

Tìm các thao tác biến đổi dữ liệu:

* Encode/decode.

* Hash.

* Encrypt/decrypt.

* Serialize/deserialize.

* JSON parse/stringify.

* Base64.

* HMAC/signature.

* String concatenation.

* Compression.

* Type conversion.

### Input

JSON

```
{
  "session_id": "sess_01",
  "source": {
    "type": "value",
    "value_hash": "sha256:abc123"
  },
  "transformation_types": [
    "encode",
    "hash",
    "encrypt",
    "serialize",
    "concatenate"
  ],
  "direction": "both",
  "max_depth": 5,
  "include_arguments": false
}
```

### Output

JSON

```
{
  "transformations": [
    {
      "transformation_id": "trans_01",
      "type": "base64_encode",
      "function_name": "btoa",
      "execution_id": "exec_30",
      "input": {
        "value_ref": "val_01",
        "type": "string"
      },
      "output": {
        "value_ref": "val_02",
        "type": "string"
      },
      "confidence": 1.0,
      "evidence": {
        "type": "direct_observation",
        "event_id": "evt_50"
      }
    }
  ]
}
```

### Phân loại bằng chứng

|
Evidence

|

Ý nghĩa

|
| --- | --- |
|

`direct_observation`

|

Hook trực tiếp function hoặc operation

|
|

`argument_match`

|

Input được match với argument

|
|

`return_match`

|

Output được match với return

|
|

`value_hash_match`

|

Match bằng hash

|
|

`static_analysis`

|

Phân tích source code

|
|

`heuristic`

|

Suy luận heuristic

|

Không nên gọi mọi operation có tên `encrypt` là mã hóa thực sự nếu chưa xác định được implementation.

## 4.5. `compare_lineage`

### Mục đích

So sánh lineage của:

* Hai request.

* Hai session.

* Hai phiên bản ứng dụng.

* Hai user flow.

* Hai cách tạo cùng một field.

### Input

JSON

```
{
  "left": {
    "session_id": "sess_01",
    "request_id": "req_10"
  },
  "right": {
    "session_id": "sess_02",
    "request_id": "req_20"
  },
  "compare_fields": [
    "headers.Authorization",
    "query.user_id",
    "body.signature"
  ],
  "include_structural_diff": true,
  "include_value_diff": false
}
```

### Output

JSON

```
{
  "comparisons": [
    {
      "field": "headers.Authorization",
      "left": {
        "origin": "localStorage.auth_token",
        "transformations": [
          "base64_encode"
        ]
      },
      "right": {
        "origin": "cookie.session",
        "transformations": [
          "hash"
        ]
      },
      "differences": [
        "Different storage source",
        "Different transformation chain"
      ]
    }
  ]
}
```

Không nên so sánh plaintext secret mặc định. So sánh nên dựa trên:

* Hash.

* Type.

* Length.

* Structure.

* Transformation sequence.

* Source lineage.

# 5. Network Tools

File:

```
interfaces/mcp/tools/network.py
```

Tương ứng:

```
application/network/summarize_request.py
application/network/compare_requests.py
application/network/find_request_dependencies.py
```

## 5.1. `summarize_request`

### Mục đích

Tóm tắt một HTTP request và các thành phần liên quan.

### Input

JSON

```
{
  "session_id": "sess_01",
  "request_id": "req_20",
  "include_headers": true,
  "include_query": true,
  "include_body_schema": true,
  "include_response": true,
  "include_lineage": true,
  "redaction_mode": "strict"
}
```

### Output

JSON

```
{
  "request": {
    "request_id": "req_20",
    "method": "POST",
    "url": "https://example.com/api/v1/data",
    "url_template": "/api/v1/data",
    "host": "example.com",
    "path": "/api/v1/data",
    "status": 200,
    "duration_ms": 142
  },
  "query_parameters": [
    {
      "name": "user_id",
      "type": "integer",
      "value_ref": "val_01",
      "lineage_status": "observed"
    }
  ],
  "headers": [
    {
      "name": "Authorization",
      "value_type": "token",
      "redacted": true,
      "origin": "localStorage.auth_token"
    }
  ],
  "body": {
    "content_type": "application/json",
    "schema": {
      "user_id": "integer",
      "action": "string"
    }
  },
  "response": {
    "status_code": 200,
    "content_type": "application/json",
    "body_size": 1240
  }
}
```

`redaction_mode`:

```
strict
standard
privileged
```

`privileged` chỉ nên được sử dụng khi có cơ chế authorization riêng.

## 5.2. `compare_requests`

### Mục đích

So sánh hai HTTP request để xác định khác biệt về:

* Method.

* URL.

* Query.

* Headers.

* Body.

* Thời gian.

* Các field động.

* Lineage.

### Input

JSON

```
{
  "left_request_id": "req_10",
  "right_request_id": "req_20",
  "session_id": "sess_01",
  "compare": {
    "method": true,
    "url": true,
    "headers": true,
    "query": true,
    "body": true,
    "lineage": true
  },
  "ignore_fields": [
    "headers.Date",
    "headers.Authorization"
  ]
}
```

### Output

JSON

```
{
  "same_endpoint": true,
  "differences": [
    {
      "location": "body.user_id",
      "type": "value_difference",
      "left": {
        "type": "integer",
        "value_hash": "sha256:a"
      },
      "right": {
        "type": "integer",
        "value_hash": "sha256:b"
      }
    },
    {
      "location": "query.timestamp",
      "type": "dynamic_field",
      "classification": "timestamp"
    }
  ],
  "lineage_differences": [
    {
      "field": "body.user_id",
      "left_origin": "response.body.user.id",
      "right_origin": "storage.local.user_id"
    }
  ]
}
```

## 5.3. `find_request_dependencies`

### Mục đích

Xác định request nào phụ thuộc vào request trước đó.

Ví dụ:

```
POST /login
    ↓ response.token
GET /profile
    ↓ response.user.id
POST /order
```

### Input

JSON

```
{
  "session_id": "sess_01",
  "request_id": "req_30",
  "direction": "upstream",
  "max_depth": 5,
  "dependency_types": [
    "value",
    "storage",
    "ordering",
    "authentication"
  ],
  "min_confidence": 0.7
}
```

### Output

JSON

```
{
  "request_id": "req_30",
  "dependencies": [
    {
      "request_id": "req_10",
      "dependency_type": "value",
      "field_mapping": [
        {
          "source": "response.body.user.id",
          "target": "request.body.user_id"
        }
      ],
      "confidence": 0.94,
      "evidence": [
        "value_hash_match",
        "temporal_order"
      ]
    },
    {
      "request_id": "req_20",
      "dependency_type": "authentication",
      "field_mapping": [
        {
          "source": "response.body.token",
          "target": "headers.Authorization"
        }
      ],
      "confidence": 0.88
    }
  ]
}
```

### Dependency types

|
Type

|

Ý nghĩa

|
| --- | --- |
|

`value`

|

Giá trị response được sử dụng trong request

|
|

`storage`

|

Request đọc dữ liệu được lưu từ request trước

|
|

`authentication`

|

Token/session được dùng lại

|
|

`ordering`

|

Request cần request trước hoàn thành

|
|

`control_flow`

|

Response quyết định request tiếp theo

|
|

`unknown`

|

Có dấu hiệu phụ thuộc nhưng chưa xác định được

|

Cần tránh coi mọi request xảy ra sau một request khác là dependency dữ liệu.

# 6. Replay Tools

File:

```
interfaces/mcp/tools/replay.py
```

Tương ứng:

```
application/replay/prepare_replay.py
application/replay/resolve_dependencies.py
application/replay/execute_replay.py
application/replay/validate_replay.py
```

Replay là nhóm có rủi ro cao hơn các tool phân tích. Nên tách thành hai cấp:

```
analysis / dry-run
actual execution
```

Mặc định MCP chỉ được phép chuẩn bị và kiểm tra replay. Việc gửi request thực tế cần explicit approval hoặc policy phù hợp.

## 6.1. `prepare_replay`

### Mục đích

Tạo replay plan từ một request đã capture.

### Input

JSON

```
{
  "session_id": "sess_01",
  "request_id": "req_20",
  "mode": "dry_run",
  "replace_dynamic_values": true,
  "resolve_dependencies": true,
  "redaction_mode": "strict",
  "target_environment": "local_test"
}
```

### Output

JSON

```
{
  "replay_plan_id": "replay_01",
  "request_id": "req_20",
  "status": "prepared",
  "steps": [
    {
      "step": 1,
      "operation": "resolve_dependency",
      "field": "headers.Authorization",
      "source": "localStorage.auth_token",
      "status": "requires_input"
    },
    {
      "step": 2,
      "operation": "send_request",
      "method": "POST",
      "url": "https://example.com/api/v1/data",
      "status": "blocked"
    }
  ],
  "safety": {
    "requires_approval": true,
    "external_network": true,
    "contains_sensitive_fields": true
  }
}
```

## 6.2. `resolve_replay_dependencies`

### Mục đích

Xác định giá trị cần thiết để replay request.

Ví dụ:

* Token.

* Cookie.

* CSRF token.

* Nonce.

* Timestamp.

* Signature.

* ID lấy từ response trước.

### Input

JSON

```
{
  "replay_plan_id": "replay_01",
  "resolve_mode": "analyze_only",
  "allow_live_capture": false,
  "fields": [
    "headers.Authorization",
    "body.signature"
  ]
}
```

### Output

JSON

```
{
  "dependencies": [
    {
      "field": "headers.Authorization",
      "status": "resolved",
      "source_type": "storage",
      "source": "localStorage.auth_token",
      "requires_secret_access": true
    },
    {
      "field": "body.signature",
      "status": "unresolved",
      "reason": "Transformation implementation was not captured",
      "possible_sources": [
        "function_return:generateSignature"
      ]
    }
  ],
  "ready_for_replay": false
}
```

### Các trạng thái dependency

```
resolved
unresolved
ambiguous
redacted
expired
requires_user_input
unsafe
```

Không nên tự động lấy lại secret từ browser hoặc Android nếu chưa có policy rõ ràng.

## 6.3. `validate_replay_plan`

### Mục đích

Kiểm tra replay plan mà không gửi request thực tế.

### Input

JSON

```
{
  "replay_plan_id": "replay_01",
  "validation_level": "strict"
}
```

### Kiểm tra

* URL có đúng target được cho phép không.

* HTTP method.

* Header bắt buộc.

* Body schema.

* Dependency đã được resolve chưa.

* Token có hết hạn không nếu xác định được.

* Có field dynamic chưa được tạo lại không.

* Có dấu hiệu request ngoài scope không.

### Output

JSON

```
{
  "valid": false,
  "checks": [
    {
      "name": "required_headers",
      "status": "passed"
    },
    {
      "name": "authentication",
      "status": "warning",
      "message": "Authorization value is redacted"
    },
    {
      "name": "signature",
      "status": "failed",
      "message": "Signature generation dependency unresolved"
    }
  ],
  "blocking_issues": [
    "signature dependency unresolved"
  ]
}
```

## 6.4. `execute_replay`

### Mục đích

Thực hiện replay đã được chuẩn bị và phê duyệt.

### Input

JSON

```
{
  "replay_plan_id": "replay_01",
  "approval_token": "approval_reference",
  "execution_mode": "single",
  "max_attempts": 1,
  "allow_external_network": false
}
```

### Output

JSON

```
{
  "replay_execution_id": "replay_exec_01",
  "status": "blocked",
  "reason": "External network access is disabled by policy",
  "request": {
    "method": "POST",
    "url": "https://example.com/api/v1/data"
  }
```
