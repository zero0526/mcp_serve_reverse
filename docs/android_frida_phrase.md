# Phase 6: Android Instrumentation với Frida

## 1. Mục tiêu của Phase 6

Phase 6 bổ sung khả năng quan sát và phân tích runtime bên trong ứng dụng Android bằng Frida.

Ở các phase trước, hệ thống chủ yếu quan sát được:

* Browser event.

* HTTP request/response.

* DOM và JavaScript.

* Dependency graph.

* Lineage ở tầng network và browser.

Frida giúp mở rộng quan sát xuống tầng ứng dụng:

```
Android App
 ├── Java/Kotlin Methods
 ├── Native C/C++ Functions
 ├── Runtime Variables
 ├── Crypto / Encoding Operations
 ├── Network Client
 └── Request Parameter Construction
```

Mục tiêu không phải là hook mọi hàm, mà là xác định:

> Hàm nào tạo ra dữ liệu, dữ liệu được biến đổi như thế nào, và biến đổi đó liên quan ra sao đến request cuối cùng?

Phạm vi nên giới hạn ở ứng dụng và môi trường Android được phép kiểm thử, ưu tiên emulator hoặc thiết bị test do bạn kiểm soát.

# 2. Vị trí của Phase 6

```
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
       ▼
Phase 6: Android Frida Instrumentation
       │
       ├── Java Runtime Observation
       ├── Native Runtime Observation
       ├── Method Call Trace
       ├── Argument / Return Capture
       ├── Runtime Correlation
       └── Evidence Integration
```

Frida không nên là một hệ thống độc lập tách khỏi lineage. Các sự kiện từ Frida cần được đưa về cùng mô hình event và graph của hệ thống.

# 3. Kiến trúc tổng thể

```
                    MCP Query / Replay
                           │
                           ▼
                  Instrumentation Service
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
        Session Manager          Policy Manager
               │                       │
               └───────────┬───────────┘
                           ▼
                    Frida Controller
                           │
                    ADB / Frida
                           │
                           ▼
                    Android Device
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
          Java Hooks            Native Hooks
                │                     │
                └──────────┬──────────┘
                           ▼
                    Event Collector
                           │
                           ▼
                 Normalization Pipeline
                           │
                           ▼
                   Graph / Lineage
```

## Các thành phần chính

|
Thành phần

|

Trách nhiệm

|
| --- | --- |
|

`Frida Controller`

|

Attach, spawn, detach và quản lý agent

|
|

`Device Manager`

|

Quản lý emulator/device và ADB

|
|

`Instrumentation Policy`

|

Kiểm soát process, class, method và dữ liệu được thu thập

|
|

`Java Hook Manager`

|

Quản lý hook Java/Kotlin

|
|

`Native Hook Manager`

|

Quản lý hook native

|
|

`Event Collector`

|

Nhận event từ Frida agent

|
|

`Correlation Engine`

|

Liên kết event runtime với request và browser event

|
|

`Evidence Store`

|

Lưu bằng chứng gốc và metadata

|
|

`Safety Manager`

|

Kiểm soát secret, scope và lifecycle

|

# 4. Phạm vi instrumentation

Không nên bắt đầu bằng native hook hoặc hook toàn bộ ứng dụng. Nên triển khai theo từng tầng.

## 4.1. Process-level observation

Thu thập thông tin cơ bản:

```
Package name
Process name
PID
UID
Architecture
App version
Android version
Frida version
```

Ví dụ:

JSON

```
{
  "process": {
    "package_name": "com.example.app",
    "process_name": "com.example.app",
    "pid": 12345,
    "architecture": "arm64",
    "app_version": "1.0.0"
  }
}
```

Definition of Done: Có thể xác nhận đúng process mục tiêu trước khi cài instrumentation.

## 4.2. Java/Kotlin method observation

Theo dõi các method được xác định trước trong ứng dụng test.

Ví dụ về nhóm hàm có thể quan sát:

```
Input handling
Serialization
Request builder
URL construction
Parameter normalization
Response parsing
```

Event nên có:

JSON

```
{
  "event_type": "JAVA_METHOD_CALL",
  "class_name": "com.example.RequestBuilder",
  "method_name": "buildPayload",
  "thread_id": 12,
  "depth": 3,
  "timestamp_ns": 1720000000000
}
```

Không nên ghi toàn bộ argument và return value mặc định. Cần có policy cho từng method:

JSON

```
{
  "method": "buildPayload",
  "capture": {
    "arguments": true,
    "return_value": true,
    "stack_trace": true
  },
  "redaction_profile": "strict"
}
```

## 4.3. Native observation

Native instrumentation nên được triển khai sau Java layer.

Các nhóm mục tiêu có thể gồm:

```
JNI bridge
Native request preparation
Serialization
Application-owned native functions
```

Các vấn đề cần xử lý:

* ABI: `arm64-v8a`, `armeabi-v7a`, `x86_64`.

* Symbol bị strip.

* Dynamic library loading.

* JNI registration động.

* ASLR.

* Khác biệt giữa debug và release build.

* Crash khi hook sai calling convention.

Không nên đặt mục tiêu hook mọi hàm native trong phiên bản đầu tiên. Phạm vi cần được giới hạn bằng module, symbol hoặc address đã được xác minh.

# 5. Frida Agent và Controller

Nên tách thành hai phần.

## 5.1. Frida Agent

Chạy trong process Android và thực hiện:

* Đăng ký hook.

* Thu thập event.

* Chuẩn hóa dữ liệu cơ bản.

* Gửi event về controller.

* Xử lý enable/disable hook.

Agent không nên chứa business logic phức tạp hoặc tự quyết định lưu trữ dài hạn.

```
Frida Agent
 ├── Hook Registry
 ├── Event Builder
 ├── Local Rate Limiter
 ├── Redaction Helper
 └── Message Transport
```

## 5.2. Frida Controller

Chạy trên máy Linux:

* Kết nối tới Frida server hoặc Frida Gadget.

* Xác định process.

* Load agent.

* Gửi configuration.

* Nhận event.

* Quản lý lifecycle.

* Ghi log và metrics.

  Frida Controller
  ├── Device Connection
  ├── Process Selector
  ├── Agent Loader
  ├── Configuration Sender
  ├── Event Receiver
  └── Session Lifecycle

Không nên để MCP gọi trực tiếp Frida API. MCP chỉ gọi application service.

# 6. Instrumentation Session

Mỗi lần instrumentation cần có session riêng.

## Schema đề xuất

JSON

```
{
  "schema_version": "instrumentation.session.v1",
  "session_id": "instr-001",
  "device": {
    "device_id": "emulator-5554",
    "android_version": "test-version",
    "architecture": "x86_64"
  },
  "target": {
    "package_name": "com.example.app",
    "process_name": "com.example.app"
  },
  "mode": "ATTACH",
  "policy_id": "policy-001",
  "status": "CREATED",
  "agent_version": "agent-v1"
}
```

## Session lifecycle

```
CREATED
   │
   ▼
VALIDATING
   │
   ▼
AUTHORIZED
   │
   ▼
CONNECTING
   │
   ▼
ATTACHING
   │
   ▼
INSTRUMENTING
   │
   ├── PAUSED
   ├── FAILED
   └── STOPPING
          │
          ▼
       STOPPED
```

Các trạng thái cần được ghi thành event để có thể debug lỗi kết nối hoặc crash.

# 7. Attach và Spawn

Hai phương thức chính có ý nghĩa khác nhau.

## 7.1. Attach

Kết nối vào process đang chạy.

```
Start App
   │
   ▼
Find Process
   │
   ▼
Attach
   │
   ▼
Load Agent
```

Ưu điểm:

* Phù hợp khi ứng dụng đã chạy.

* Dễ dùng trong exploratory analysis.

* Không nhất thiết phải khởi động lại app.

Hạn chế:

* Có thể bỏ lỡ các hàm được gọi lúc khởi động.

* Một số initialization đã hoàn thành trước khi attach.

* Process có thể có cơ chế chống instrumentation.

## 7.2. Spawn

Khởi chạy ứng dụng thông qua instrumentation controller trước khi resume.

```
Spawn Process
   │
   ▼
Load Agent
   │
   ▼
Install Hooks
   │
   ▼
Resume Process
```

Ưu điểm:

* Quan sát được giai đoạn khởi động.

* Có thể bắt các initialization event sớm.

* Phù hợp khi cần theo dõi state được tạo ngay lúc startup.

Hạn chế:

* Có thể thay đổi timing của ứng dụng.

* Một số ứng dụng phản ứng khác với spawn.

* Cần xử lý lifecycle và crash cẩn thận.

Nên hỗ trợ cả hai, nhưng phải ghi rõ mode vào report.

# 8. Hook Registry

Không nên hard-code hook trực tiếp trong một file agent lớn.

## Schema đề xuất

JSON

```
{
  "hook_id": "hook-001",
  "runtime": "JAVA",
  "target": {
    "class_name": "com.example.RequestBuilder",
    "method_name": "buildPayload"
  },
  "capture_policy": {
    "arguments": true,
    "return_value": true,
    "stack_trace": false
  },
  "enabled": true,
  "version": "1"
}
```

## Hook registry cần hỗ trợ

* Hook ID.

* Runtime.

* Target specification.

* Version.

* Enable/disable.

* Capture policy.

* Sampling policy.

* Redaction policy.

* Expected output schema.

Ví dụ:

```
Hook Registry
 ├── java.request_builder
 ├── java.serializer
 ├── java.response_parser
 └── native.jni_bridge
```

Không nên cho MCP client tự gửi mã hook tùy ý. Nên dùng hook definition đã được kiểm duyệt và đăng ký.

# 9. Event Model

Frida event cần tương thích với event model của Phase 1.

## Event envelope

JSON

```
{
  "schema_version": "runtime.event.v1",
  "event_id": "event-001",
  "instrumentation_session_id": "instr-001",
  "timestamp_ns": 1720000000000,
  "process": {
    "pid": 12345,
    "package_name": "com.example.app"
  },
  "thread": {
    "id": 12,
    "name": "OkHttp Dispatcher"
  },
  "event_type": "JAVA_METHOD_CALL",
  "payload": {},
  "provenance": {
    "source": "frida",
    "agent_version": "agent-v1"
  }
}
```

## Các loại event

Python

Chạy

```
class RuntimeEventType(str, Enum):
    PROCESS_ATTACHED = "PROCESS_ATTACHED"
    PROCESS_DETACHED = "PROCESS_DETACHED"
    JAVA_METHOD_CALL = "JAVA_METHOD_CALL"
    JAVA_METHOD_RETURN = "JAVA_METHOD_RETURN"
    NATIVE_FUNCTION_CALL = "NATIVE_FUNCTION_CALL"
    NATIVE_FUNCTION_RETURN = "NATIVE_FUNCTION_RETURN"
    FIELD_READ = "FIELD_READ"
    FIELD_WRITE = "FIELD_WRITE"
    THREAD_CREATED = "THREAD_CREATED"
    EXCEPTION = "EXCEPTION"
    MODULE_LOADED = "MODULE_LOADED"
    NETWORK_CORRELATION = "NETWORK_CORRELATION"
    AGENT_ERROR = "AGENT_ERROR"
```

Không nhất thiết phải triển khai toàn bộ loại event ngay từ đầu.

MVP nên có:

```
PROCESS_ATTACHED
JAVA_METHOD_CALL
JAVA_METHOD_RETURN
MODULE_LOADED
EXCEPTION
AGENT_ERROR
```

# 10. Call Correlation

Đây là phần quan trọng nhất để tích hợp với lineage.

Một method call có thể chứa:

```
timestamp
thread_id
call_id
parent_call_id
stack depth
arguments
return value
```

Ví dụ:

JSON

```
{
  "event_type": "JAVA_METHOD_CALL",
  "call_id": "call-100",
  "parent_call_id": "call-90",
  "thread_id": 12,
  "class_name": "com.example.PayloadBuilder",
  "method_name": "build",
  "arguments": {
    "query": "laptop"
  }
}
```

Khi method trả về:

JSON

```
{
  "event_type": "JAVA_METHOD_RETURN",
  "call_id": "call-100",
  "return_value": {
    "query": "laptop",
    "page": 1
  }
}
```

`call_id` là khóa liên kết giữa call và return.

Cần xử lý:

* Method exception.

* Recursive call.

* Multi-thread.

* Async callback.

* Thread pool.

* Method không return do process crash.

* Hook reentrancy.

# 11. Liên kết Frida Event với Network Request

Mục tiêu:

```
Java Method
    │
    ▼
Payload Construction
    │
    ▼
Request Builder
    │
    ▼
HTTP Client
    │
    ▼
Network Request
```

Ví dụ graph:

```
runtime.call.001
      │
      │ PRODUCES
      ▼
runtime.value.001
      │
      │ USED_BY
      ▼
request.body.field.query
      │
      ▼
network.request.001
```

## Các mức correlation

### Level 1: Timestamp correlation

Liên kết event runtime với request trong khoảng thời gian.

Hạn chế: độ chính xác thấp khi có nhiều request song song.

### Level 2: Thread correlation

Sử dụng thread ID hoặc execution context.

Hạn chế: request có thể chuyển thread hoặc sử dụng asynchronous callback.

### Level 3: Explicit correlation

Đưa correlation context vào các điểm được kiểm soát trong môi trường test.

Ví dụ:

JSON

```
{
  "correlation_id": "corr-001",
  "runtime_call_id": "call-100",
  "request_id": "req-123"
}
```

### Level 4: Data-flow correlation

So sánh dữ liệu đầu ra của method với:

* Request URL.

* Query parameters.

* Headers.

* Body fields.

* Hash hoặc normalized representation.

Nên lưu evidence và phương pháp correlation, thay vì chỉ ghi một cạnh `CAUSED_BY`.

# 12. Confidence của Correlation

Không nên mặc định rằng một method chạy ngay trước request là nguyên nhân tạo request.

JSON

```
{
  "edge_type": "POTENTIAL_INFLUENCE",
  "source": "call-100",
  "target": "req-123",
  "confidence": 0.72,
  "evidence": [
    "Temporal proximity",
    "Matching payload field"
  ],
  "method": "TIMESTAMP_AND_DATA_MATCH"
}
```

Các trạng thái:

```
OBSERVED
SUPPORTED
INFERRED
UNKNOWN
CONTRADICTED
```

Ví dụ:

* `OBSERVED`: method return chứa giá trị xuất hiện trong request body.

* `SUPPORTED`: nhiều bằng chứng độc lập cùng hỗ trợ quan hệ.

* `INFERRED`: quan hệ được suy ra từ timing hoặc stack.

* `UNKNOWN`: chưa đủ bằng chứng.

* `CONTRADICTED`: replay hoặc thí nghiệm cho kết quả ngược lại.

# 13. Capture Policy

Instrumentation có thể tạo ra rất nhiều event. Cần policy để tránh làm chậm ứng dụng và làm đầy storage.

## 13.1. Sampling

JSON

```
{
  "sampling": {
    "mode": "RATE",
    "rate": 0.1,
    "always_capture_errors": true
  }
}
```

Tuy nhiên, sampling ngẫu nhiên có thể làm mất chuỗi lineage. Với các call thuộc cùng một trace, nên có trace-based sampling:

```
Nếu một event được chọn:
    giữ các event liên quan trong cùng execution trace
```

## 13.2. Scope filtering

Lọc theo:

* Package.

* Class.

* Module.

* Method.

* Thread.

* Call depth.

* Khoảng thời gian.

* Loại event.

Ví dụ:

JSON

```
{
  "scope": {
    "classes": [
      "com.example.network.*",
      "com.example.serialization.*"
    ],
    "max_call_depth": 8,
    "capture_duration_ms": 30000
  }
}
```

## 13.3. Rate limit

```
max_events_per_second
max_payload_bytes
max_stack_trace_depth
max_session_storage_bytes
```

Khi vượt giới hạn:

JSON

```
{
  "event_type": "CAPTURE_THROTTLED",
  "dropped_events": 1250,
  "reason": "EVENT_RATE_LIMIT"
}
```

Không nên âm thầm bỏ event. Phải ghi nhận dữ liệu đã bị mất để tránh kết luận sai về lineage.

# 14. Sensitive Data và Redaction

Runtime instrumentation có thể thu được dữ liệu nhạy cảm:

```
Access token
Refresh token
Cookie
Password
Personal information
Encryption key
Session identifier
```

Cần tách:

```
Raw Evidence
    │
    ├── Encrypted storage
    ├── Strict access control
    └── Limited retention

Analysis Representation
    │
    ├── Redacted values
    ├── Hashes
    ├── Type metadata
    └── Length / shape information
```

Ví dụ:

JSON

```
{
  "field": "authorization",
  "value": "<REDACTED>",
  "metadata": {
    "type": "STRING",
    "length": 184,
    "sha256": "sha256:..."
  }
}
```

Không nên log giá trị secret nguyên bản chỉ vì hook đang capture argument.

# 15. Native Instrumentation: Thiết kế an toàn

Native layer có rủi ro cao hơn Java layer.

Các vấn đề cần kiểm soát:

* Sai kiểu tham số.

* Sai calling convention.

* Sai offset.

* Hook nhầm địa chỉ.

* Deadlock.

* Reentrancy.

* Memory access lỗi.

* Crash process.

* Overhead lớn.

* Khác biệt ABI.

Nên có các chế độ:

```
OBSERVE_ONLY
SAFE_CAPTURE
DISABLED
```

Trong phiên bản đầu tiên, ưu tiên:

1. Quan sát module được load.

2. Quan sát các symbol đã xác định trong ứng dụng test.

3. Thu thập metadata tối thiểu.

4. Không sửa giá trị return.

5. Không patch instruction.

6. Không bypass cơ chế bảo vệ của ứng dụng bên thứ ba.

Mục tiêu Phase 6 là runtime observability, không phải thay đổi hành vi bảo mật của ứng dụng.

# 16. Instrumentation Configuration

Nên sử dụng cấu hình có version.

JSON

```
{
  "schema_version": "instrumentation.config.v1",
  "config_id": "config-001",
  "target": {
    "package_name": "com.example.app"
  },
  "hooks": [
    {
      "hook_id": "java.payload_builder",
      "enabled": true
    }
  ],
  "capture": {
    "arguments": true,
    "return_values": true,
    "stack_traces": false,
    "max_payload_bytes": 4096
  },
  "limits": {
    "max_events_per_second": 1000,
    "max_duration_ms": 60000
  },
  "redaction_profile": "strict"
}
```

Config phải được kiểm tra trước khi gửi đến agent.

# 17. MCP Tools cho Phase 6

## 17.1. `list_android_devices`

Liệt kê thiết bị được phép sử dụng.

JSON

```
{
  "devices": [
    {
      "device_id": "emulator-5554",
      "status": "ONLINE",
      "architecture": "x86_64"
    }
  ]
}
```

## 17.2. `list_target_processes`

Chỉ hiển thị process trong scope được cấp quyền.

JSON

```
{
  "device_id": "emulator-5554"
}
```

## 17.3. `create_instrumentation_session`

Tạo session nhưng chưa attach.

JSON

```
{
  "device_id": "emulator-5554",
  "package_name": "com.example.app",
  "mode": "ATTACH",
  "policy_id": "policy-001"
}
```

## 17.4. `validate_instrumentation_config`

Kiểm tra:

* Target process.

* Hook registry.

* Runtime.

* Scope.

* Capture limits.

* Redaction.

* Authorization.

* Device compatibility.

## 17.5. `start_instrumentation`

Khởi động session đã được validate.

JSON

```
{
  "session_id": "instr-001"
}
```

Không nên cho phép tool tự ý chạy cấu hình chưa được kiểm tra.

## 17.6. `stop_instrumentation`

Dừng agent và cleanup:

* Hook.

* Message channel.

* Session resources.

* Temporary files.

* Event buffers.

## 17.7. `get_instrumentation_status`

JSON

```
{
  "session_id": "instr-001"
}
```

## 17.8. `search_runtime_events`

Tìm event theo:

```
session_id
event_type
class_name
method_name
thread_id
time range
request_id
```

## 17.9. `get_call_trace`

Lấy call chain của một runtime event.

JSON

```
{
  "session_id": "instr-001",
  "call_id": "call-100",
  "max_depth": 20
}
```

## 17.10. `correlate_runtime_with_request`

Tìm bằng chứng liên kết runtime event với request.

JSON

```
{
  "session_id": "instr-001",
  "runtime_event_id": "event-001",
  "request_id": "req-123"
}
```

## 17.11. `analyze_runtime_lineage`

Tạo lineage từ:

```
Method Call
 → Return Value
 → Data Transformation
 → Request Field
```

Response phải thể hiện mức độ chắc chắn và evidence.

## 17.12. `get_instrumentation_report`

Trả về:

* Session status.

* Hook status.

* Event count.

* Dropped event count.

* Errors.

* Runtime overhead.

* Correlated requests.

* Lineage findings.

# 18. Storage Model

Có thể mở rộng storage hiện tại bằng các bảng hoặc event stream sau.

## `instrumentation_sessions`

```
id
device_id
package_name
process_name
mode
policy_id
agent_version
status
started_at
finished_at
```

## `hook_definitions`

```
id
runtime
target_spec
config_json
version
is_enabled
```

## `runtime_events`

```
id
session_id
event_type
process_id
thread_id
timestamp_ns
call_id
parent_call_id
payload_ref
provenance_json
```

## `runtime_values`

```
id
event_id
value_type
normalized_value
raw_value_ref
redaction_status
```

## `runtime_request_links`

```
id
runtime_event_id
request_id
relation_type
confidence
correlation_method
evidence_json
```

Payload lớn nên được lưu ngoài bảng chính:

```
PostgreSQL → Metadata / Index
Object Storage → Raw Event Payload
Search Index → Runtime Event Search
Graph Store → Call and Data Dependencies
```

# 19. Runtime Overhead

Instrumentation làm thay đổi timing và có thể ảnh hưởng đến hành vi app.

Cần đo:

```
Hook execution time
Events per second
Agent message latency
CPU overhead
Memory overhead
Dropped events
App crash count
Network timing deviation
```

Ví dụ report:

JSON

```
{
  "performance": {
    "events_total": 12000,
    "events_dropped": 30,
    "avg_hook_overhead_us": 18,
    "estimated_cpu_overhead_percent": 3.2
  }
}
```

Các số liệu chỉ có ý nghĩa khi có baseline không instrumentation để so sánh.

Không nên kết luận rằng một request có timing gốc chỉ dựa trên phiên bản đang bị hook.

# 20. Failure Handling

|
Error

|

Ý nghĩa

|
| --- | --- |
|

`DEVICE_OFFLINE`

|

Thiết bị không khả dụng

|
|

`PROCESS_NOT_FOUND`

|

Không tìm thấy process

|
|

`ATTACH_FAILED`

|

Attach thất bại

|
|

`SPAWN_FAILED`

|

Spawn thất bại

|
|

`AGENT_LOAD_FAILED`

|

Không load được agent

|
|

`HOOK_INSTALL_FAILED`

|

Hook không được cài

|
|

`CLASS_NOT_FOUND`

|

Không tìm thấy class

|
|

`METHOD_NOT_FOUND`

|

Không tìm thấy method

|
|

`ABI_UNSUPPORTED`

|

ABI không được hỗ trợ

|
|

`AGENT_CRASHED`

|

Agent gặp lỗi

|
|

`EVENT_BACKPRESSURE`

|

Collector không xử lý kịp

|
|

`POLICY_DENIED`

|

Bị policy từ chối

|
|

`SESSION_EXPIRED`

|

Session đã hết hạn

|

Mỗi error cần chứa:

JSON

```
{
  "error_code": "HOOK_INSTALL_FAILED",
  "message": "Hook target could not be resolved",
  "retryable": false,
  "context": {
    "hook_id": "java.payload_builder"
  }
}
```

Không nên tự động retry hook native không xác định vì có thể làm process crash lặp lại.

# 21. Tích hợp với Phase 5: Replay + Frida

Đây là phần có giá trị thực tế cao.

```
Replay Plan
    │
    ▼
Start Android App
    │
    ▼
Start Frida Instrumentation
    │
    ▼
Execute UI / Network Action
    │
    ▼
Capture Runtime Events
    │
    ▼
Capture Network Requests
    │
    ▼
Correlate Runtime → Request
    │
    ▼
Compare with Baseline
```

Ví dụ workflow:

```
1. Mở ứng dụng test.
2. Bật instrumentation.
3. Nhập giá trị vào form.
4. Click Submit.
5. Thu thập method call.
6. Thu thập request.
7. So sánh payload với baseline.
```

Replay report nên ghi rõ:

JSON

```
{
  "execution": {
    "browser_replay": false,
    "android_replay": true,
    "instrumentation_session_id": "instr-001"
  },
  "evidence": {
    "runtime_events": 250,
    "correlated_requests": 4,
    "uncorrelated_requests": 1
  }
}
```

# 22. Tích hợp với Counterfactual Replay

Phase 5 có thể tạo variant, còn Phase 6 quan sát cách ứng dụng biến đổi input.

```
Baseline:
Input A
  │
  ▼
Method Chain A
  │
  ▼
Request Payload A

Variant:
Input B
  │
  ▼
Method Chain B
  │
  ▼
Request Payload B
```

So sánh:

* Call sequence.

* Method arguments.

* Return values.

* Branch behavior.

* Payload fields.

* Network request.

* Runtime exception.

* Timing.

Ví dụ:

JSON

```
{
  "intervention": {
    "field": "search_query",
    "baseline": "laptop",
    "variant": "phone"
  },
  "observed_changes": [
    {
      "method": "buildPayload",
      "argument_changed": true
    },
    {
      "field": "$.query",
      "request_value_changed": true
    }
  ],
  "conclusion": {
    "status": "SUPPORTED",
    "confidence": "HIGH"
  }
}
```

`HIGH` ở đây chỉ nên phản ánh policy đánh giá bằng chứng của hệ thống, không phải chứng minh quan hệ nhân quả tuyệt đối.

# 23. Bảo vệ hệ thống Instrumentation

## Device isolation

* Dùng emulator hoặc thiết bị test.

* Không sử dụng credential thật.

* Tách mạng test nếu có thể.

* Hạn chế outbound network.

* Xóa state sau phiên test.

## Access control

Phân quyền theo:

```
Device
Package
Process
Hook profile
Capture data
Raw evidence
```

Một user có quyền đọc lineage không nhất thiết có quyền:

* Attach vào process.

* Đọc raw argument.

* Xem secret.

* Chạy native instrumentation.

## Audit log

Ghi lại:

```
Ai tạo session
Target nào
Policy nào
Hook nào được bật
Thời điểm attach
Thời điểm detach
Dữ liệu nào được truy cập
```

# 24. Testing Strategy

## 24.1. Unit tests

* Event schema.

* Hook configuration.

* Policy validation.

* Redaction.

* Call stack reconstruction.

* Correlation scoring.

* State machine.

* Rate limiter.

## 24.2. Agent tests

Trên ứng dụng Android test do bạn sở hữu:

* Method được gọi.

* Return value được ghi nhận.

* Exception được xử lý.

* Hook có thể enable/disable.

* Agent detach không để lại trạng thái không hợp lệ.

* Event bị giới hạn đúng khi vượt rate.

## 24.3. Integration tests

```
Controller
  → Device
  → Process
  → Agent
  → Event Collector
  → Event Store
  → Graph Projection
```

## 24.4. Stability tests

* Attach/detach nhiều lần.

* Process restart.

* App crash.

* Device offline.

* Agent message overflow.
