# Phase 5: Replay

## 1. Mục tiêu của Phase 5

Replay là giai đoạn cho phép hệ thống tái hiện lại một phiên hoạt động của trình duyệt dựa trên dữ liệu đã thu thập ở Phase 1–4.

Thay vì chỉ trả lời:

> Request này được tạo từ đâu? Dữ liệu nào đã ảnh hưởng đến nó?

Hệ thống có thể tiến thêm một bước:

> Nếu thực hiện lại chuỗi thao tác và điều kiện tương tự, request có được tạo ra giống trước không? Nếu khác, khác ở đâu và tại sao?

Replay không đơn thuần là phát lại HTTP request. Nó cần phân biệt:

* Deterministic replay: tái hiện chính xác với cùng input và trạng thái.

* Approximate replay: tái hiện gần giống nhưng có thể khác do môi trường.

* Exploratory replay: thử thay đổi một input hoặc điều kiện để quan sát tác động.

# 2. Vị trí của Replay trong toàn hệ thống

```
Browser Runtime
      │
      ▼
Phase 1: Capture
      │
      ▼
Phase 2: Graph Projection
      │
      ▼
Phase 3: Lineage Analysis
      │
      ▼
Phase 4: MCP Query Layer
      │
      ▼
Phase 5: Replay
      │
      ├── Replay Plan
      ├── State Reconstruction
      ├── Action Execution
      ├── Network Observation
      ├── Result Comparison
      └── Replay Report
```

Replay sử dụng kết quả từ các phase trước:

|
Phase

|

Dữ liệu được Replay sử dụng

|
| --- | --- |
|

Phase 1

|

Event, request, response, browser state

|
|

Phase 2

|

Dependency graph, execution graph

|
|

Phase 3

|

Lineage, nguyên nhân và đường dẫn dữ liệu

|
|

Phase 4

|

Query API, tool contract, authorization

|
|

Phase 5

|

Tái hiện, kiểm tra và so sánh hành vi

|

Nguyên tắc quan trọng: Replay không nên tự xây dựng lại logic lineage hoặc truy cập trực tiếp database. Nó nên sử dụng các service và projection đã được chuẩn hóa ở các phase trước.

# 3. Phạm vi Replay

Nên chia Replay thành nhiều mức độ thay vì triển khai tất cả ngay từ đầu.

## 3.1. Request-level replay

Phát lại một HTTP request đã được ghi nhận.

```
Captured Request
      │
      ▼
Normalize Request
      │
      ▼
Reconstruct Headers / Query / Body
      │
      ▼
Execute Request
      │
      ▼
Compare Response
```

Ví dụ:

JSON

```
{
  "method": "POST",
  "url": "https://example.test/api/search",
  "headers": {
    "content-type": "application/json"
  },
  "body": {
    "query": "laptop"
  }
}
```

Request-level replay hữu ích cho:

* Kiểm tra tính tái lập của API.

* So sánh response theo thời gian.

* Phân tích sự thay đổi của request.

* Kiểm tra request có phụ thuộc vào token hoặc trạng thái trước đó không.

Tuy nhiên, request-level replay không tái hiện đầy đủ hành vi của ứng dụng nếu request phụ thuộc vào:

* Cookie phiên.

* CSRF token.

* Access token.

* Nonce.

* Timestamp.

* Request trước đó.

* Browser state.

* JavaScript-generated value.

## 3.2. Action-level replay

Phát lại hành động người dùng hoặc hành động trong browser.

Ví dụ:

```
Open Page
    │
    ▼
Click Login
    │
    ▼
Fill Username
    │
    ▼
Fill Password
    │
    ▼
Submit Form
    │
    ▼
Observe API Request
```

Các action có thể gồm:

JSON

```
{
  "type": "CLICK",
  "target": {
    "selector": "[data-testid='submit']"
  }
}
```

JSON

```
{
  "type": "FILL",
  "target": {
    "selector": "#search",
    "value": "laptop"
  }
}
```

JSON

```
{
  "type": "NAVIGATE",
  "url": "https://example.test/search"
}
```

Action-level replay phù hợp để kiểm tra:

* Chuỗi thao tác dẫn đến request.

* Sự phụ thuộc giữa UI event và network event.

* Trình tự tạo token hoặc payload.

* Thay đổi hành vi khi input khác nhau.

## 3.3. Workflow-level replay

Tái hiện một chuỗi hành động hoàn chỉnh.

```
Workflow
 ├── Navigate
 ├── Login
 ├── Open Product Page
 ├── Change Quantity
 ├── Click Checkout
 └── Capture Checkout Request
```

Workflow-level replay cần quản lý:

* Thứ tự thực thi.

* Điều kiện trước mỗi bước.

* Kết quả đầu ra của bước trước.

* Biến runtime.

* Timeout.

* Retry.

* Checkpoint.

* Failure recovery.

Đây nên là mục tiêu chính của Phase 5 sau khi request-level replay đã ổn định.

# 4. Replay không đồng nghĩa với gửi lại request

Đây là điểm cần thiết kế rõ ngay từ đầu.

Một request đã capture có thể chứa:

http

```
Authorization: Bearer eyJ...
Cookie: session=...
X-CSRF-Token: ...
X-Request-Id: ...
```

Nếu gửi lại nguyên trạng:

* Token có thể đã hết hạn.

* Request ID có thể phải unique.

* Cookie có thể không còn hợp lệ.

* Server có thể phát hiện replay.

* Request có thể gây side effect lần thứ hai.

* Có thể làm thay đổi dữ liệu thật.

Vì vậy, mỗi trường dữ liệu phải được phân loại theo chiến lược replay.

|
Loại dữ liệu

|

Chiến lược

|
| --- | --- |
|

Static value

|

Giữ nguyên

|
|

Derived value

|

Tính lại

|
|

Session token

|

Lấy từ session replay

|
|

Timestamp

|

Giữ hoặc tái tạo theo policy

|
|

Random nonce

|

Tạo mới hoặc cố định khi test

|
|

Request ID

|

Thường tạo mới

|
|

Cookie

|

Khôi phục từ browser state

|
|

CSRF token

|

Tái lấy từ flow

|
|

Sensitive secret

|

Không lưu hoặc redacted

|

Ví dụ:

JSON

```
{
  "field": "x-csrf-token",
  "classification": "DERIVED",
  "replay_strategy": "REGENERATE_FROM_STATE"
}
```

# 5. Kiến trúc đề xuất

```
MCP Replay Tool
       │
       ▼
Replay Application Service
       │
       ├── Replay Authorization
       ├── Replay Plan Builder
       ├── State Manager
       ├── Action Scheduler
       ├── Browser Adapter
       ├── Network Observer
       ├── Safety Guard
       ├── Result Comparator
       └── Replay Report Builder
              │
              ▼
       Replay Storage
```

## 5.1. Các thành phần chính

### Replay Planner

Chuyển yêu cầu replay thành một kế hoạch thực thi.

Input:

JSON

```
{
  "session_id": "session-001",
  "target_request_id": "req-123",
  "mode": "WORKFLOW",
  "max_steps": 30
}
```

Output:

JSON

```
{
  "replay_plan_id": "plan-001",
  "steps": [
    {
      "step_id": "step-1",
      "action": "NAVIGATE",
      "depends_on": []
    },
    {
      "step_id": "step-2",
      "action": "CLICK",
      "depends_on": ["step-1"]
    },
    {
      "step_id": "step-3",
      "action": "CAPTURE_REQUEST",
      "depends_on": ["step-2"]
    }
  ]
}
```

Planner không nên tự động suy diễn không có căn cứ. Mỗi step cần có:

* Nguồn dữ liệu.

* Độ tin cậy.

* Điều kiện thực thi.

* Quan hệ dependency.

* Trạng thái `OBSERVED`, `INFERRED` hoặc `UNKNOWN`.

### State Manager

Quản lý trạng thái cần thiết cho replay.

Có thể bao gồm:

```
Browser State
 ├── URL
 ├── Cookies
 ├── Local Storage
 ├── Session Storage
 ├── IndexedDB snapshot
 ├── DOM checkpoint
 ├── Authentication state
 └── Runtime variables
```

Không phải mọi trạng thái đều có thể hoặc nên khôi phục trực tiếp.

Nên phân loại:

|
State

|

Cách xử lý

|
| --- | --- |
|

URL

|

Khôi phục trực tiếp

|
|

Cookie

|

Khôi phục nếu được cấp quyền

|
|

Local storage

|

Snapshot có kiểm soát

|
|

DOM

|

Dùng làm checkpoint, không coi là source of truth

|
|

Access token

|

Tái tạo hoặc lấy từ flow

|
|

Server-side session

|

Không giả định có thể clone

|
|

IndexedDB

|

Chỉ hỗ trợ khi adapter xác định được tính nhất quán

|

Không nên lưu plaintext credential hoặc token dài hạn trong Replay Plan.

### Action Executor

Thực thi các bước thông qua browser adapter.

Python

Chạy

```
class ActionExecutor(Protocol):
    async def navigate(self, url: str) -> ActionResult:
        ...

    async def click(self, target: Target) -> ActionResult:
        ...

    async def fill(self, target: Target, value: str) -> ActionResult:
        ...

    async def evaluate(self, script_id: str, args: dict) -> ActionResult:
        ...

    async def wait_for(self, condition: WaitCondition) -> ActionResult:
        ...
```

Không nên cho phép MCP client truyền JavaScript tùy ý vào `evaluate`.

Thay vào đó, sử dụng:

JSON

```
{
  "script_id": "extract_visible_text",
  "arguments": {
    "selector": "#result"
  }
}
```

Các script được whitelist và version hóa.

### Network Observer

Theo dõi network event phát sinh trong quá trình replay.

Cần liên kết:

```
Replay Step
    │
    ├── Browser Event
    ├── Request
    ├── Response
    ├── Console Event
    └── Error Event
```

Ví dụ:

JSON

```
{
  "replay_step_id": "step-4",
  "observed_requests": [
    {
      "request_id": "replay-req-001",
      "method": "POST",
      "url": "/api/search",
      "timestamp_ns": 1720000000000
    }
  ]
}
```

Network Observer cần xử lý trường hợp:

* Một action tạo nhiều request.

* Request được tạo bất đồng bộ.

* Request xuất hiện trước hoặc sau một khoảng delay.

* Request bị retry.

* Request bị abort.

* Request được tạo bởi service worker.

# 6. Replay Modes

Nên định nghĩa mode rõ ràng trong API.

Python

Chạy

```
class ReplayMode(str, Enum):
    REQUEST = "REQUEST"
    ACTION = "ACTION"
    WORKFLOW = "WORKFLOW"
    DRY_RUN = "DRY_RUN"
    EXPLORATORY = "EXPLORATORY"
```

## 6.1. `DRY_RUN`

Chỉ tạo kế hoạch và kiểm tra điều kiện, không thực thi side effect.

```
Validate Plan
    │
    ├── Check permissions
    ├── Check target
    ├── Check action support
    ├── Check sensitive operations
    └── Return execution preview
```

Đây nên là mode mặc định trước khi cho phép replay thật.

## 6.2. `REQUEST`

Chỉ phát lại request, thường thông qua một isolated HTTP client hoặc browser context.

Phải có policy:

JSON

```
{
  "allow_external_network": false,
  "allow_state_mutation": false,
  "allowed_hosts": [
    "example.test"
  ]
}
```

## 6.3. `ACTION`

Thực thi từng action trong browser.

Ví dụ:

JSON

```
{
  "mode": "ACTION",
  "actions": [
    {
      "type": "NAVIGATE",
      "url": "https://example.test"
    },
    {
      "type": "CLICK",
      "target": {
        "role": "button",
        "name": "Search"
      }
    }
  ]
}
```

## 6.4. `WORKFLOW`

Thực thi nhiều bước có dependency và checkpoint.

JSON

```
{
  "mode": "WORKFLOW",
  "workflow_id": "wf-001",
  "start_from": "step-3",
  "stop_after": "step-8"
}
```

Việc cho phép `start_from` yêu cầu checkpoint tương thích. Không thể giả định rằng state tại step 3 có thể được tái tạo chỉ bằng cách mở lại URL.

## 6.5. `EXPLORATORY`

Thực hiện replay với một hoặc nhiều biến thay đổi.

Ví dụ:

```
Original:
    search = "laptop"

Variant:
    search = "phone"
```

Hoặc:

```
Original:
    quantity = 1

Variant:
    quantity = 3
```

Mỗi variant phải được cô lập:

```
Baseline Run
    │
    ├── Variant A
    ├── Variant B
    └── Variant C
```

Không nên chạy các variant dùng chung mutable browser state nếu muốn kết quả có thể so sánh.

# 7. Replay Plan

Replay Plan là artifact trung tâm của Phase 5.

## 7.1. Schema đề xuất

JSON

```
{
  "schema_version": "replay.plan.v1",
  "plan_id": "plan-001",
  "source_session_id": "session-001",
  "target": {
    "type": "REQUEST",
    "id": "req-123"
  },
  "mode": "WORKFLOW",
  "environment": {
    "browser": "chromium",
    "viewport": {
      "width": 1280,
      "height": 720
    },
    "locale": "en-US",
    "timezone": "UTC"
  },
  "steps": [],
  "limits": {
    "max_steps": 50,
    "max_duration_ms": 60000,
    "max_requests": 100
  },
  "safety": {
    "dry_run": true,
    "allowed_hosts": [
      "example.test"
    ],
    "allow_mutations": false
  }
}
```

## 7.2. Các thuộc tính nên có

|
Thuộc tính

|

Ý nghĩa

|
| --- | --- |
|

`plan_id`

|

Định danh kế hoạch

|
|

`source_session_id`

|

Session gốc

|
|

`target`

|

Request/action/workflow cần replay

|
|

`mode`

|

Chế độ thực thi

|
|

`steps`

|

Danh sách thao tác

|
|

`environment`

|

Browser và môi trường

|
|

`limits`

|

Giới hạn tài nguyên

|
|

`safety`

|

Chính sách an toàn

|
|

`version`

|

Phiên bản plan

|
|

`created_by`

|

Caller hoặc agent tạo plan

|

# 8. Step Model

Mỗi bước cần có schema thống nhất.

JSON

```
{
  "step_id": "step-5",
  "sequence": 5,
  "type": "CLICK",
  "target": {
    "selector": "[data-testid='submit']",
    "role": "button"
  },
  "preconditions": [
    {
      "type": "ELEMENT_VISIBLE"
    }
  ],
  "timeout_ms": 5000,
  "retry_policy": {
    "max_attempts": 2,
    "backoff_ms": 200
  },
  "expected_effects": [
    {
      "type": "NETWORK_REQUEST",
      "method": "POST",
      "path": "/api/submit"
    }
  ]
}
```

Các loại step có thể gồm:

```
NAVIGATE
CLICK
FILL
SELECT
PRESS_KEY
WAIT
ASSERT
CAPTURE_REQUEST
EXTRACT_VALUE
SET_VARIABLE
CHECKPOINT
```

Không nên đưa quá nhiều loại action vào phiên bản đầu tiên. Có thể bắt đầu với:

```
NAVIGATE
CLICK
FILL
WAIT
CAPTURE_REQUEST
ASSERT
```

# 9. Preconditions và Postconditions

Replay cần kiểm tra điều kiện trước và sau mỗi step.

## 9.1. Preconditions

Ví dụ:

JSON

```
{
  "type": "ELEMENT_VISIBLE",
  "selector": "#submit"
}
```

JSON

```
{
  "type": "URL_MATCH",
  "pattern": "/checkout"
}
```

JSON

```
{
  "type": "VARIABLE_EXISTS",
  "name": "csrf_token"
}
```

## 9.2. Postconditions

Ví dụ:

JSON

```
{
  "type": "REQUEST_OBSERVED",
  "method": "POST",
  "path": "/api/checkout"
}
```

JSON

```
{
  "type": "URL_MATCH",
  "pattern": "/success"
}
```

JSON

```
{
  "type": "DOM_TEXT_CONTAINS",
  "selector": "#result",
  "value": "Success"
}
```

Điều này giúp phân biệt:

* Action thực thi thành công.

* Action thực thi nhưng không tạo ra expected effect.

* Action thất bại do precondition.

* Action tạo ra kết quả khác với baseline.

# 10. Replay Execution Lifecycle

```
CREATED
   │
   ▼
VALIDATING
   │
   ├── INVALID ──────► FAILED
   │
   ▼
AUTHORIZED
   │
   ▼
PREPARING
   │
   ▼
RUNNING
   │
   ├── PAUSED
   ├── CANCELLED
   ├── TIMEOUT
   ├── FAILED
   │
   ▼
COMPARING
   │
   ▼
COMPLETED
```

## Trạng thái đề xuất

Python

Chạy

```
class ReplayStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    AUTHORIZED = "AUTHORIZED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPARING = "COMPARING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
```

Mỗi lần thay đổi trạng thái nên được ghi lại thành event:

JSON

```
{
  "replay_id": "replay-001",
  "event_type": "STATUS_CHANGED",
  "from": "RUNNING",
  "to": "COMPARING",
  "timestamp_ns": 1720000000000
}
```

Điều này giúp debug replay bị dừng ở đâu và vì sao.

# 11. Isolation và Safety

Đây là phần cần được ưu tiên trước việc tối ưu tốc độ.

## 11.1. Browser isolation

Mỗi replay nên có một execution context riêng:

```
Replay A → Browser Context A
Replay B → Browser Context B
Replay C → Browser Context C
```

Không nên dùng chung:

* Cookie mutable.

* Local storage.

* Session storage.

* Page instance.

* Runtime variables.

Nếu bắt buộc dùng state chung, phải đánh dấu rõ:

JSON

```
{
  "state_policy": "SHARED_READ_ONLY"
}
```

## 11.2. Host allowlist

Replay không nên mặc định truy cập mọi host.

JSON

```
{
  "allowed_hosts": [
    "localhost",
    "example.test"
  ],
  "blocked_hosts": [
    "metadata.google.internal",
    "169.254.169.254"
  ]
}
```

Cần kiểm tra cả:

* Hostname.

* IP resolve.

* Redirect.

* DNS rebinding.

* IPv4 và IPv6.

* Proxy routing.

* URL trong iframe hoặc worker.

## 11.3. Mutation policy

Phân loại request theo mức độ side effect:

|
Nhóm

|

Ví dụ

|

Policy

|
| --- | --- | --- |
|

Read-only

|

`GET /products`

|

Có thể cho phép

|
|

Potential mutation

|

`POST /search`

|

Cần kiểm tra

|
|

State mutation

|

`POST /order`

|

Chặn mặc định

|
|

Destructive

|

Delete account

|

Chặn mặc định

|
|

Authentication

|

Login/token

|

Cần policy riêng

|

Không nên chỉ dựa vào HTTP method. Một số `GET` vẫn có thể tạo side effect, và một số `POST` có thể chỉ là truy vấn.

## 11.4. Human approval

Với hành động có side effect, yêu cầu approval rõ ràng.

JSON

```
{
  "requires_approval": true,
  "reason": "Request may modify server-side state",
  "risk": "HIGH"
}
```

Replay engine không nên tự động vượt qua approval bằng cách suy diễn rằng user đã đồng ý từ việc tạo plan.

# 12. Request Normalization

Để so sánh request gốc và request replay, cần chuẩn hóa trước.

## 12.1. Các trường cần loại bỏ hoặc thay thế

```
Date
Timestamp
Nonce
Request ID
Tracing ID
Dynamic token
Cookie
Authorization
```

Ví dụ:

JSON

```
{
  "method": "POST",
  "path": "/api/search",
  "body": {
    "query": "laptop",
    "timestamp": "<DYNAMIC>",
    "nonce": "<DYNAMIC>"
  }
}
```

## 12.2. Canonical representation

JSON

```
{
  "method": "POST",
  "normalized_url": "/api/search",
  "headers": {
    "content-type": "application/json"
  },
  "body_hash": "sha256:...",
  "semantic_body": {
    "query": "laptop"
  }
}
```

Nên lưu cả hai:

* Raw evidence được bảo vệ.

* Normalized representation dùng cho so sánh.

Không nên hash toàn bộ request mà không lưu thông tin về các trường dynamic, vì khi đó khó giải thích nguyên nhân khác biệt.

# 13. Response Comparison

So sánh response không nên chỉ dựa vào HTTP status code.

## 13.1. Các tầng so sánh

### Tầng 1: Transport

```
HTTP status
Response time
Protocol error
Connection error
Redirect chain
```

### Tầng 2: Headers

```
Content-Type
Cache-Control
Set-Cookie
Content-Length
```

Các header dynamic nên được bỏ qua hoặc normalize.

### Tầng 3: Body

```
Exact equality
Canonical JSON equality
Selected field comparison
Schema compatibility
Semantic similarity
```

### Tầng 4: Side effects

```
New requests
Storage changes
Navigation changes
DOM changes
Console errors
```

## 13.2. Comparison result

JSON

```
{
  "comparison": {
    "status": "DIFFERENT",
    "transport_match": true,
    "status_code_match": true,
    "headers_match": false,
    "body_match": false,
    "side_effect_match": false
  },
  "differences": [
    {
      "path": "$.data.results[0].price",
      "baseline": 100,
      "replay": 120,
      "classification": "DYNAMIC_VALUE"
    }
  ]
}
```

## 13.3. Các kết quả không nên chỉ có `PASS/FAIL`

Python

Chạy

```
class ComparisonStatus(str, Enum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    BLOCKED = "BLOCKED"
```

Ví dụ:

* `INCONCLUSIVE`: response thay đổi nhưng chưa xác định nguyên nhân.

* `NOT_COMPARABLE`: replay không thể khôi phục session gốc.

* `BLOCKED`: bị chặn bởi safety policy.

* `DIFFERENT`: có khác biệt đã được xác định.

# 14. Replay Report

Replay Report cần trả lời được bốn câu hỏi:

1. Replay có thực thi thành công không?

2. Đã thực thi được những bước nào?

3. Request/response nào khác với baseline?

4. Nguyên nhân được xác định ở mức nào?

## Schema đề xuất

JSON

```
{
  "schema_version": "replay.report.v1",
  "replay_id": "replay-001",
  "status": "COMPLETED",
  "source": {
    "session_id": "session-001",
    "target_request_id": "req-123"
  },
  "execution": {
    "started_at_ns": 1720000000000,
    "finished_at_ns": 1720000005000,
    "duration_ms": 5000,
    "completed_steps": 8,
    "failed_steps": 0
  },
  "observations": {
    "requests": 12,
    "responses": 12,
    "console_errors": 1
  },
  "comparison": {
    "status": "DIFFERENT",
    "matched_requests": 10,
    "different_requests": 2
  },
  "warnings": [],
  "provenance": {
    "replay_engine_version": "replay-v1",
    "comparison_version": "comparison-v1"
  }
}
```

# 15. Replay với Lineage

Đây là điểm tạo ra giá trị lớn cho hệ thống của bạn.

Replay không chỉ phát lại workflow mà còn có thể kiểm tra giả thuyết từ Phase 3.

Ví dụ, lineage phân tích cho rằng:

```
User Input
   │
   ▼
JavaScript Function A
   │
   ▼
Variable B
   │
   ▼
Request Payload
   │
   ▼
POST /api/search
```

Replay có thể kiểm tra:

1. Thay đổi `User Input`.

2. Chạy lại workflow.

3. Quan sát `Variable B`.

4. So sánh request payload.

5. Kiểm tra dependency có còn tồn tại không.

   Baseline:
   input = "laptop"
   payload.query = "laptop"

   Variant:
   input = "phone"
   payload.query = "phone"

Kết quả có thể được biểu diễn:

JSON

```
{
  "hypothesis": {
    "source_node": "input-001",
    "target_node": "payload-001",
    "relation": "INFLUENCES"
  },
  "validation": {
    "status": "SUPPORTED",
    "observations": [
      "Changing source input changed target payload"
    ]
  }
}
```

Tuy nhiên, cần phân biệt:

* Observed: giá trị thực tế được quan sát.

* Supported: replay cung cấp bằng chứng hỗ trợ giả thuyết.

* Proven: không nên dùng từ này nếu chỉ có một số lần replay.

* Inconclusive: chưa đủ dữ liệu để kết luận.

Một lần replay thành công không chứng minh dependency luôn đúng trong mọi trường hợp.

# 16. Counterfactual Replay

Counterfactual replay dùng để kiểm tra câu hỏi:

> Nếu thay đổi biến X nhưng giữ các điều kiện khác tương tự, output Y có thay đổi không?

Ví dụ:

```
X = Search Keyword
Y = Request Body
```

Hoặc:

```
X = UI Selection
Y = API Parameter
```

## Thiết kế

```
Original Run
     │
     ├── Capture baseline
     │
     ▼
Create Variant
     │
     ├── Change selected input
     ├── Preserve environment
     └── Preserve workflow
     │
     ▼
Replay Variant
     │
     ▼
Compare Lineage and Output
```

## Điều kiện để kết quả có giá trị

* Chỉ thay đổi biến mục tiêu nếu có thể.

* Cô lập execution context.

* Ghi nhận các biến môi trường.

* Chạy nhiều lần nếu có tính ngẫu nhiên.

* Kiểm tra các yếu tố gây nhiễu.

* Không kết luận nhân quả chỉ từ tương quan của hai output.

Có thể lưu:

JSON

```
{
  "experiment_id": "exp-001",
  "baseline_run_id": "run-baseline",
  "variant_run_id": "run-variant",
  "interventions": [
    {
      "variable": "search_query",
      "before": "laptop",
      "after": "phone"
    }
  ],
  "confounders": [
    "server_timestamp",
    "session_state"
  ]
}
```

# 17. MCP Tools cho Phase 5

MCP Layer nên expose các tool có giới hạn rõ ràng.

## 17.1. `create_replay_plan`

Tạo kế hoạch, chưa thực thi.

JSON

```
{
  "session_id": "session-001",
  "target_type": "REQUEST",
  "target_id": "req-123",
  "mode": "WORKFLOW"
}
```

Response:

JSON

```
{
  "plan_id": "plan-001",
  "status": "CREATED",
  "requires_approval": true,
  "steps": []
}
```

## 17.2. `validate_replay_plan`

Kiểm tra:

* Schema.

* Target tồn tại.

* Browser adapter hỗ trợ action.

* Host policy.

* State availability.

* Side effect risk.

* Resource limits.

## 17.3. `preview_replay`

Trả về execution preview:

JSON

```json
{
  "plan_id": "plan-001",
  "estimated_steps": 8,
  "potential_requests": 12,
  "requires_approval": true
}
```

---

# 18. Báo Cáo Triển Khai Hoàn Thành Thực Tế (Implementation Report)

Phase 3: **Replay Engine & Code Synthesis** đã được hoàn thiện toàn diện, kế thừa trực tiếp hợp đồng bàn giao `ReplaySpec` từ Phase 2 và tổ chức theo tiêu chuẩn Clean Architecture & DRY.

## 18.1. Sơ Đồ Kiến Trúc

```
app/
├── domain/replay/
│   ├── entities.py              # ReplayMode, ReplayRequest, ReplayExecutionResult, ReplayComparison, SynthesizedCode
│   └── policies.py              # ReplaySafetyPolicy, VariableResolver (nội suy {{var}}, timestamp, nonce)
├── ports/
│   └── replay.py                # HTTPReplayExecutorPort, CodeSynthesizerPort
├── adapters/
│   ├── replay/
│   │   └── http_client.py       # HttpxReplayExecutor (sử dụng httpx.AsyncClient độc lập, đo latency)
│   └── synthesis/
│       └── code_synthesizer.py  # CodeSynthesizer (Python httpx, cURL bash, TypeScript fetch)
├── application/replay/
│   ├── prepare_replay.py        # PrepareReplayUseCase (biến đổi ReplaySpec thành ReplayRequest)
│   ├── compare_responses.py     # CompareResponsesUseCase (so sánh vi phân status, headers, json diff)
│   ├── execute_replay.py        # ExecuteReplayUseCase (điều phối DRY_RUN và EXECUTE + so sánh baseline)
│   └── synthesize_code.py       # SynthesizeCodeUseCase (sinh mã nguồn tự động)
└── interfaces/mcp/tools/
    └── replay.py                # MCP tools: prepare_replay_tool, execute_replay_tool, synthesize_code_tool
```

## 18.2. Các Tính Năng Đã Triển Khai

1. **Replay Modes:**
   - `DRY_RUN`: Chuẩn bị request, nội suy biến, kiểm tra an toàn mà không phát sinh lưu lượng mạng ra ngoài.
   - `EXECUTE`: Gửi request thực tế qua HTTP client độc lập, đo đạc latency, đọc baseline từ `network_responses` và thực hiện so sánh vi phân.
   - `EXPLORATORY`: Thử nghiệm các biến đầu vào khác nhau để phân tích sự thay đổi phản hồi.
2. **Dynamic Variable Resolution (`VariableResolver`):**
   - Thay thế các placeholder `{{var}}` trong URL, Headers, và Body.
   - Hỗ trợ điền giá trị người dùng nhập (`user_inputs`).
   - Tự động sinh `timestamp` dạng epoch millisecond và `nonce` / `uuid` nếu không được truyền vào.
3. **Safety Guard & Policies (`ReplaySafetyPolicy`):**
   - Whitelist host (`allowed_hosts`), kiểm tra HTTP Method được phép, bảo vệ chống side-effects ngoài ý muốn (trả về 403 / 405 nếu vi phạm).
4. **Automated Response Comparison (`CompareResponsesUseCase`):**
   - So sánh status code, content-type.
   - So sánh có cấu trúc cho JSON body: phát hiện missing keys, extra keys, type mismatches.
   - Tính toán chỉ số tương đồng `match_score` (từ 0.0 đến 1.0).
5. **Multi-Language Code Synthesis (`CodeSynthesizer`):**
   - **Python (`httpx`):** Hàm `async def execute_request(...)` hoàn chỉnh, typed arguments, docstring chi tiết nguồn gốc Lineage từng tham số, tự đóng connection an toàn. Cú pháp được kiểm chứng hợp lệ bằng AST parser.
   - **cURL:** Lệnh bash curl nhiều dòng với đầy đủ headers và escaped payload.
   - **TypeScript (`fetch`):** TypeScript interface và async function `executeRequest` chuẩn ES module.
6. **MCP Tools Interface:**
   - Cung cấp 3 tool chuẩn mcp: `prepare_replay_tool`, `execute_replay_tool`, `synthesize_code_tool`.

## 18.3. Kết Quả Kiểm Thử (Verification)

Toàn bộ 3 pha (Phase 1, Phase 2, Phase 3) đều vượt qua 100% test tự động:
- `tests/test_phase1_capture.py` (Multi-session capture, stealth engine, pre-seed state)
- `tests/test_phase2_lineage.py` (Graph projection, backward/forward traversal, differential analysis, ReplaySpec)
- `tests/test_phase3_replay_synthesis.py` (Substitution, DRY_RUN, EXECUTE, response comparison, Python/cURL/TS code synthesis, MCP tools)

