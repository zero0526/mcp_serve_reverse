# Phase 1: Browser Capture và Event Store

## 1. Mục tiêu

Phase 1 tập trung xây dựng hệ thống capture và lưu trữ event từ trình duyệt, sử dụng Playwright kết hợp JavaScript instrumentation.

Hệ thống cần thu thập được:

* HTTP request/response.

* `fetch` và `XMLHttpRequest`.

* Function execution trong JavaScript.

* Đọc/ghi `localStorage`, `sessionStorage`, cookie.

* Các thao tác serialize/deserialize.

* Runtime error và console log.

* Quan hệ context giữa function execution và network request.

Phase này chưa thực hiện phân tích lineage hoàn chỉnh. Dữ liệu được thu thập sẽ là nền tảng cho các phase sau.

# 2. Kiến trúc Browser Capture

```
                    MCP / CLI
                       │
                       ▼
              StartCaptureSession
                       │
                       ▼
                 BrowserSession
                       │
                       ▼
                 Playwright
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   Playwright Events       JavaScript Instrumentation
          │                         │
          │                 ┌───────┴────────┐
          │                 ▼                ▼
          │              fetch/XHR       runtime/storage
          │
          └────────────┬────────────┘
                       ▼
                    JS Bridge
                       │
                       ▼
                    EventSink
                       │
                       ▼
                IngestEventUseCase
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Validate     Normalize    Redact
          │            │            │
          └────────────┴────────────┘
                       │
                       ▼
                  Event Store
                       │
              ┌────────┴────────┐
              ▼                 ▼
           SQLite            JSONL
```

## Thành phần tương ứng với project

```
app/
├── adapters/browser/
│   ├── browser_session.py
│   ├── js_bridge.py
│   ├── network_mapper.py
│   ├── playwright_capture.py
│   └── instrumentation/
│       ├── cookie.js
│       ├── fetch.js
│       ├── runtime.js
│       ├── serializer.js
│       ├── storage.js
│       └── xhr.js
├── application/
│   ├── capture/
│   │   ├── capture_status.py
│   │   ├── start_session.py
│   │   └── stop_session.py
│   └── ingest/
│       ├── ingest_event.py
│       ├── normalize_event.py
│       └── validate_event.py
├── domain/
│   └── trace/
│       ├── entities.py
│       ├── events.py
│       ├── provenance.py
│       └── value_objects.py
├── infrastructure/
│   └── serialization/
│       ├── json.py
│       └── redaction.py
└── ports/
    ├── capture.py
    └── event_store.py
```

# 3. Browser Session Lifecycle

## 3.1. Các trạng thái

```
CREATED
   │
   ▼
STARTING
   │
   ├── lỗi khởi tạo ──► FAILED
   │
   ▼
RUNNING
   │
   ▼
STOPPING
   │
   ▼
STOPPED
```

Định nghĩa:

Python

Chạy

```
# app/domain/shared/enums.py

from enum import StrEnum


class SessionStatus(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
```

## 3.2. `BrowserSession`

File:

```
app/adapters/browser/browser_session.py
```

Chịu trách nhiệm:

* Khởi tạo **CloakBrowser** (Stealth Chromium C++ patched binary từ `CloakHQ/cloakbrowser`) với fallback sang Playwright tiêu chuẩn.
* Xóa bỏ hoàn toàn cờ nhận diện bot tự động (`navigator.webdriver = false`, che giấu `__playwright__binding__`, random fingerprint seed, bézier human mouse curves).
* Tạo browser context và hỗ trợ nạp trước state (**Pre-Seed State**: cookies, localStorage, sessionStorage) để bỏ qua các bước đăng nhập / 2FA lặp lại.
* Tạo page và cấu hình proxy.
* Cấy bundle instrumentation (`storage.js`, `fetch.js`, `xhr.js`, `cookie.js`, `runtime.js`, `serializer.js`) vào context trước khi mã nguồn trang thực thi.
* Điều phối cầu nối sự kiện hai chế độ (**Hybrid Event Bridge**):
  - **Stealth Event Queue Drain**: Hàng đợi in-page (`window.__api_lineage_queue__`) được drain ngầm định kỳ (50ms) và flush khi đóng session, giúp truyền sự kiện về Python mà không để lộ CDP `exposeBinding` (vốn bị các anti-bot như Cloudflare / Kasada quét dấu vết).
  - **CDP Bridge Binding**: Tương thích ngược với standard Playwright khi CDP binding khả dụng.
* Quản lý vòng đời (start / stop / lifecycle).

Không nên để `BrowserSession`:

* Ghi trực tiếp vào SQLite.

* Tính lineage.

* Phân tích signature.

* Thực hiện replay.

* Tạo MCP response.

Ví dụ interface:

Python

Chạy

```
from typing import Protocol


class BrowserSessionPort(Protocol):
    async def start(self, session_id: str, target: str | None) -> None:
        ...

    async def stop(self, session_id: str) -> None:
        ...

    async def health_check(self, session_id: str) -> bool:
        ...
```

# 4. Session Database

## 4.1. Schema

SQL

```
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,

    source TEXT NOT NULL DEFAULT 'browser'
        CHECK (source = 'browser'),

    name TEXT NOT NULL,
    target TEXT,

    status TEXT NOT NULL,

    started_at_ns INTEGER,
    ended_at_ns INTEGER,

    created_at_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    CHECK (
        ended_at_ns IS NULL
        OR started_at_ns IS NULL
        OR ended_at_ns >= started_at_ns
    )
);
```

Trong browser-only version, `source` luôn là `browser`. Tuy nhiên vẫn nên giữ trường này để phân biệt loại nguồn trong tương lai nếu cần.

### 4.1.1. Khái niệm Task & Multi-Session Grouping (`task_id`)

Khi reverse engineer một luồng nghiệp vụ phức tạp (ví dụ: *Đổi tên hiển thị Facebook*), một phiên capture đơn lẻ là **không đủ** để phân biệt giữa:
* Dữ liệu tĩnh (API version, constant payload flags, client identifiers).
* Dữ liệu biến đổi theo người dùng (input name, user id).
* Dữ liệu động sinh ra bởi client runtime (CSRF token, timestamp, HMAC signatures, dynamic nonces).

Do đó, hệ thống áp dụng mô hình **Task Grouping**:
* **1 Task** đại diện cho một mục tiêu phân tích (ví dụ: `task_fb_change_name`).
* Mỗi Task bao gồm **2-3 Sessions** độc lập:
  * *Session 1:* Thực hiện thao tác với bộ tham số A (ví dụ: đổi tên thành "Nguyen An").
  * *Session 2:* Thực hiện cùng thao tác với bộ tham số B (ví dụ: đổi tên thành "Tran Binh").
  * *Session 3 (Tùy chọn):* Thực hiện thao tác với tham số không hợp lệ để bắt luồng xử lý lỗi hoặc xác thực phụ.
* Trường `task_id` được lưu trữ trực tiếp trong `metadata_json` (hoặc cột `task_id`) để các Phase sau (Phase 2: Graph Projection và Phase 3: Differential Analysis) có thể truy vấn và so sánh đối chiếu (diff) đồ thị giữa các session.

## 4.2. Metadata mẫu

JSON

```
{
  "browser": {
    "engine": "chromium",
    "headless": false,
    "version": "unknown"
  },
  "capture": {
    "network": true,
    "runtime": true,
    "storage": true,
    "crypto": false,
    "screenshots": false
  },
  "instrumentation": {
    "version": "0.1.0",
    "scripts": [
      "fetch",
      "xhr",
      "storage",
      "runtime"
    ]
  }
}
```

Không lưu cookie, token hoặc thông tin xác thực trong `metadata_json`.

# 5. Event Envelope

Mọi dữ liệu từ Playwright và JavaScript instrumentation phải được chuyển về một schema thống nhất.

## 5.1. Schema tổng quát

JSON

```
{
  "event_id": "evt_01JABC",
  "schema_version": 1,
  "session_id": "sess_01",

  "source": "browser",
  "event_type": "network_request",

  "timestamp_ns": 1726830000000000000,
  "sequence": 102,

  "page_id": "page_01",
  "frame_id": "frame_01",

  "execution_id": "exec_10",
  "parent_execution_id": "exec_09",

  "payload": {},
  "metadata": {
    "adapter": "playwright",
    "instrumentation_version": "0.1.0"
  }
}
```

## 5.2. Browser-specific fields

|
Trường

|

Mục đích

|
| --- | --- |
|

`page_id`

|

Xác định tab/page

|
|

`frame_id`

|

Xác định frame/iframe

|
|

`execution_id`

|

Function execution liên quan

|
|

`parent_execution_id`

|

Quan hệ gọi function

|
|

`sequence`

|

Thứ tự event được capture

|
|

`timestamp_ns`

|

Thời điểm quan sát

|

`frame_id` đặc biệt quan trọng vì một page có thể chứa nhiều iframe.

## 5.3. Pydantic model

Python

Chạy

```
# app/domain/trace/value_objects.py

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: str = Field(min_length=1, max_length=256)
    schema_version: int = Field(ge=1)

    session_id: str
    source: str = "browser"
    event_type: str

    timestamp_ns: int = Field(ge=0)
    sequence: int | None = Field(default=None, ge=0)

    page_id: str | None = None
    frame_id: str | None = None

    execution_id: str | None = None
    parent_execution_id: str | None = None

    payload: dict
    metadata: dict = Field(default_factory=dict)
```

# 6. Các loại Browser Event

File:

```
app/domain/trace/events.py
```

Python

Chạy

```
from enum import StrEnum


class EventType(StrEnum):
    # JavaScript runtime
    FUNCTION_CALL = "function_call"
    FUNCTION_RETURN = "function_return"
    FUNCTION_THROW = "function_throw"

    # Network
    NETWORK_REQUEST = "network_request"
    NETWORK_RESPONSE = "network_response"
    NETWORK_FAILED = "network_failed"

    # Storage
    STORAGE_READ = "storage_read"
    STORAGE_WRITE = "storage_write"
    STORAGE_DELETE = "storage_delete"

    # Serialization
    SERIALIZE = "serialize"
    DESERIALIZE = "deserialize"

    # Runtime
    CONSOLE_LOG = "console_log"
    RUNTIME_ERROR = "runtime_error"

    # Browser lifecycle
    PAGE_CREATED = "page_created"
    PAGE_NAVIGATED = "page_navigated"
    PAGE_CLOSED = "page_closed"
```

Không nên hook tất cả JavaScript function ngay từ đầu. Nên ưu tiên các API có giá trị phân tích cao.

# 7. Playwright Capture

File:

```
app/adapters/browser/playwright_capture.py
```

## 7.1. Các event Playwright nên bắt

|
Event

|

Mục đích

|
| --- | --- |
|

`request`

|

Request bắt đầu

|
|

`response`

|

Response nhận được

|
|

`requestfailed`

|

Request thất bại

|
|

`requestfinished`

|

Request hoàn thành

|
|

`console`

|

Console message

|
|

`pageerror`

|

JavaScript error

|
|

`framenavigated`

|

Navigation

|
|

`popup`

|

Popup page mới

|
|

`websocket`

|

Theo dõi WebSocket nếu cần

|

## 7.2. Network capture flow

```
page.on("request")
        │
        ▼
create request_id
        │
        ▼
capture method/url/headers/body
        │
        ▼
publish network_request
        │
        ▼
page.on("response")
        │
        ▼
match request_id
        │
        ▼
capture status/headers/body
        │
        ▼
publish network_response
```

## 7.3. Điểm cần chú ý

### 7.3.1. Cơ chế Deduplication & Request Correlation

Playwright event và JavaScript hook có thể ghi nhận cùng một request:

```
fetch instrumentation (in-page)
    └── network_request (có call stack JS, nhưng thiếu SSL/timing chi tiết)

Playwright page.on("request") (browser level)
    └── network_request (có timing chính xác, IP, nhưng thiếu JS stack)
```

Nếu không có cơ chế deduplication, một request sẽ bị lưu hai lần hoặc ghi đè sai lệch.

**Giải pháp triển khai trong Phase 1:**
1. **Correlation qua ID / Header bí mật:** Khi JavaScript hook (`fetch.js`/`xhr.js`) khởi tạo request, nó tạo một `request_id` duy nhất (ví dụ: `fetch_xyz123`). Đối với browser internal routing, có thể gắn header tạm thời `X-Lineage-Req-Id` hoặc map thông qua bộ đệm thời gian:
   $$(method, url\_normalized, timestamp \pm 200ms, body\_hash)$$
2. **Cơ chế Upsert Placeholder:**
   * Nếu Playwright `page.on("response")` đến trước khi request body được xử lý, tạo một bản ghi placeholder với `status="placeholder"`.
   * Khi sự kiện `network_request` hoàn chỉnh đến từ in-page hook, hệ thống cập nhật (upsert) bản ghi hiện có thay vì chèn dòng mới, bảo toàn tính duy nhất của khóa chính `network_requests.id`.

```json
{
  "capture_sources": [
    "playwright_network",
    "fetch_instrumentation"
  ],
  "deduplication": {
    "status": "matched",
    "confidence": 1.0,
    "strategy": "request_id_correlation"
  }
}
```

### 7.3.2. Lọc tài nguyên tĩnh & Giới hạn Scope (Filtering)

Mục tiêu của reverse engineering là phân tích **API data flow**, không phải kiểm thử hiệu năng web. Khi mở một trang web thực tế, trình duyệt sẽ tải hàng trăm file tĩnh (ảnh, font, CSS, video, tracking telemetry) gây quá tải DB và làm loãng dữ liệu đồ thị.

**Quy tắc lọc mặc định của Network Capture:**
* **Chỉ chấp nhận các resource type:** `['fetch', 'xhr', 'document', 'ping', 'other']`.
* **Bỏ qua tự động:** Các `resource_type` thuộc nhóm `['image', 'media', 'font', 'stylesheet']`, các file có đuôi mở rộng `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.woff`, `.woff2`, `.ttf`, `.css`.
* **URL Blacklist/Ignore Pattern:** Tự động bỏ qua các domain quảng cáo và thu thập analytics thông dụng (Google Analytics, Facebook Pixel, Hotjar, Sentry, Datadog) trừ khi người dùng chỉ định rõ ràng trong cấu hình capture options.

### 7.3.3. Cấu hình Anti-Bot / Anti-Detection & Chế độ Headful

Các mục tiêu lớn (Facebook, Google, TikTok, Cloudflare, Akamai) phát hiện trình duyệt tự động hóa thông qua cờ `navigator.webdriver` và fingerprinting đặc trưng của Chromium headless:

* **Tham số Launch bắt buộc:**
  ```python
  args = [
      "--disable-blink-features=AutomationControlled",
      "--no-sandbox",
      "--disable-infobars",
  ]
  ```
* **Giả lập Viewport & User-Agent:** Khởi tạo context với kích thước màn hình thực tế (ví dụ: `1280x800` hoặc `1920x1080`) và chuỗi User-Agent tiêu chuẩn của Google Chrome máy bàn.
* **Hỗ trợ Headful (`headless: false`):** Mặc định hỗ trợ tùy chọn bật giao diện trực quan để người dùng có thể tự tay vượt qua Cloudflare Turnstile, ReCaptcha, hoặc thực hiện đăng nhập thủ công khi hệ thống chưa có sẵn cookie.

### 7.3.4. Quản lý vòng đời & Graceful Shutdown (Tránh Zombie Process)

Khi người dùng đột ngột đóng cửa sổ trình duyệt (bấm nút X) hoặc tab bị crash:
* Hệ thống lắng nghe sự kiện `page.on("close")`, `context.on("close")`, và `browser.on("disconnected")`.
* Tự động flush toàn bộ hàng đợi sự kiện (async queue) đang nằm trong bộ nhớ xuống SQLite trước khi giải phóng tài nguyên.
* Cập nhật trạng thái session trong SQLite sang `STOPPED` hoặc `FAILED` kèm lý do ngắt kết nối, đảm bảo không để lại các tiến trình `google-chrome` chạy ngầm (zombie processes) chiếm dụng RAM.

# 8. JavaScript Instrumentation

## 8.1. `fetch.js`

Mục đích:

* Ghi nhận arguments của `fetch`.

* Capture URL và method.

* Capture request headers.

* Capture request body.

* Liên kết với execution context.

* Ghi nhận response metadata.

Event mẫu:

JSON

```
{
  "event_type": "network_request",
  "payload": {
    "transport": "fetch",
    "method": "POST",
    "url": "https://example.com/api/data",
    "headers": {},
    "body": {
      "type": "json",
      "value_ref": "val_01"
    }
  }
}
```

Không nên chỉ monkey-patch `fetch` mà bỏ qua native behavior. Instrumentation cần giữ:

* Promise semantics.

* `this` context.

* Error behavior.

* Response streaming behavior.

* Request cancellation.

## 8.2. `xhr.js`

Cần theo dõi:

```
open()
setRequestHeader()
send()
onreadystatechange
onload
onerror
```

Các event quan trọng:

```
xhr_open
xhr_header
xhr_send
xhr_response
xhr_error
```

Có thể normalize về các event network chung:

JSON

```
{
  "event_type": "network_request",
  "payload": {
    "transport": "xhr",
    "method": "POST",
    "url": "/api/data"
  }
}
```

## 8.3. `storage.js`

Hook:

JavaScript

```
localStorage.getItem
localStorage.setItem
localStorage.removeItem

sessionStorage.getItem
sessionStorage.setItem
sessionStorage.removeItem
```

Event mẫu:

JSON

```
{
  "event_type": "storage_read",
  "payload": {
    "storage_type": "local_storage",
    "key": "auth_token",
    "value_ref": "val_01",
    "value_type": "string",
    "value_length": 128
  }
}
```

Không gửi plaintext token về Python nếu không cần thiết. Có thể gửi:

* Value type.

* Length.

* HMAC value.

* Redacted preview.

* Key.

* Timestamp.

### 8.3.1. Cơ chế Pre-seeded State Injection (Bỏ qua Login / 2FA)

Để loại bỏ các bước trung gian lặp lại (đăng nhập tài khoản, nhập mã xác thực hai lớp SMS/TOTP, vượt qua welcome tour), hệ thống cung cấp cơ chế tiêm trước trạng thái (**Pre-seeded State**):

* **Cookie Injection:** Được nạp vào `BrowserContext` thông qua `context.add_cookies()` trước khi bất kỳ yêu cầu mạng nào được gửi đi.
* **Storage Injection (`localStorage` / `sessionStorage`):** Được nạp thông qua `add_init_script()` bằng hàm nội bộ `window.__api_lineage_apply_preseed__()`. Quá trình này hoàn tất ngay tại thời điểm môi trường DOM khởi tạo và trước khi mã JavaScript của website đích được thực thi.
* **Đánh dấu Nguồn gốc (Provenance Tracking):** Các khóa được nạp sẵn sẽ được ghi nhận vào `sessions.metadata_json` (ví dụ: `pre_seed_storage_keys: ["auth_token", "device_id"]`). Nhờ đó, Phase 2 (Graph Projection) sẽ gắn nhãn node của các giá trị này là `Root / Seed / External Input`, ngăn chặn việc suy luận sai lệch rằng giá trị token được tạo ra bởi mã JavaScript của website.

```json
{
  "cookies": [
    { "name": "c_user", "value": "10001", "domain": ".facebook.com" },
    { "name": "xs", "value": "secret_token", "domain": ".facebook.com" }
  ],
  "storage": {
    "local_storage": {
      "auth_token": "bearer_xyz123",
      "device_id": "dev_phone_emulator"
    },
    "session_storage": {
      "active_tab": "account_settings"
    }
  }
}
```

## 8.4. `cookie.js`

Cần phân biệt:

* `document.cookie` read.

* `document.cookie` write.

* Cookie được Playwright quan sát ở context.

* Cookie response từ `Set-Cookie`.

Không nên coi mọi cookie là có thể đọc được bằng JavaScript. Cookie có thuộc tính `HttpOnly` không được expose cho `document.cookie`.

## 8.5. `runtime.js`

Nên bắt đầu với các runtime event có phạm vi rõ ràng:

* Function execution được chọn.

* Runtime error.

* Console.

* Một số API quan trọng.

Không nên hook toàn bộ function của mọi object vì có thể:

* Tạo hàng triệu event.

* Làm thay đổi stack.

* Gây recursion.

* Làm ứng dụng chạy chậm.

* Tạo false positive trong lineage.

## 8.6. `serializer.js`

Có thể hỗ trợ theo dõi:

JavaScript

```
JSON.parse
JSON.stringify
```

Tuy nhiên, cần cẩn thận:

* Không serialize object có circular reference.

* Không gọi lại serializer đã bị hook.

* Không đọc getter gây side effect.

* Giới hạn độ sâu object.

* Giới hạn kích thước payload.

* Không làm lộ secret trong log.

# 9. JavaScript Bridge

File:

```
app/adapters/browser/js_bridge.py
```

Bridge chịu trách nhiệm nhận message từ JavaScript và chuyển thành `EventEnvelope`.

## 9.1. Luồng

```
JavaScript instrumentation
          │
          ▼
window event / Playwright binding
          │
          ▼
js_bridge.py
          │
          ▼
parse message
          │
          ▼
validate source metadata
          │
          ▼
create EventEnvelope
          │
          ▼
EventSink.publish()
```

## 9.2. Message format

JSON

```
{
  "bridge_version": 1,
  "type": "capture_event",
  "page_id": "page_01",
  "frame_id": "frame_01",
  "timestamp_ms": 12345,
  "event_type": "storage_read",
  "payload": {
    "storage_type": "local_storage",
    "key": "user_id"
  }
}
```

Bridge nên kiểm tra:

* Message type.

* Bridge version.

* Payload size.

* Page/frame identifier.

* Event type.

* Timestamp.

* Serialization errors.

Không nên tin tưởng mọi dữ liệu do JavaScript instrumentation gửi lên. Instrumentation chạy trong context của trang và có thể bị ứng dụng can thiệp hoặc ghi đè.

# 10. Network Mapper

File:

```
app/adapters/browser/network_mapper.py
```

Chịu trách nhiệm chuyển dữ liệu Playwright về network entity thống nhất.

## 10.1. Mapping

```
Playwright Request
       │
       ▼
NetworkRequest
       │
       ├── request_id
       ├── method
       ├── url
       ├── host
       ├── path
       ├── query
       ├── headers
       ├── body
       └── timestamp
```

## 10.2. URL normalization

Nên lưu cả URL gốc và các thành phần đã tách, nhưng cần redaction.

JSON

```
{
  "url": "https://example.com/api?user_id=123&token=[REDACTED]",
  "host": "example.com",
  "path": "/api",
  "query": {
    "user_id": {
      "value_ref": "val_01"
    },
    "token": {
      "value_ref": "val_02",
      "redacted": true
    }
  }
}
```

Các trường nên có:

```
method
url
url_template
scheme
host
port
path
query_json
headers_json
body_json
resource_type
initiator_type
```

`initiator_type` có thể nhận giá trị:

```
fetch
xhr
document
script
image
stylesheet
other
unknown
```

# 11. Event Ingestion Pipeline

File:

```
app/application/ingest/ingest_event.py
```

## 11.1. Pipeline

```
Receive
   │
   ▼
Validate envelope
   │
   ▼
Verify session
   │
   ▼
Generate payload hash
   │
   ▼
Redact sensitive data
   │
   ▼
Append event log
   │
   ▼
Normalize payload
   │
   ▼
Persist SQLite
   │
   ▼
Publish ingestion result
```

## 11.2. Application service

Python

Chạy

```
class IngestEventUseCase:
    def __init__(
        self,
        validator,
        normalizer,
        event_store,
        redactor,
        clock,
    ):
        self.validator = validator
        self.normalizer = normalizer
        self.event_store = event_store
        self.redactor = redactor
        self.clock = clock

    async def execute(self, event):
        self.validator.validate(event)

        redacted_event = self.redactor.apply(event)

        normalized = self.normalizer.normalize(redacted_event)

        return await self.event_store.persist(
            event=redacted_event,
            normalized=normalized,
            ingested_at_ns=self.clock.now_ns(),
        )
```

Application layer không nên biết event đến từ `page.on("request")` hay `fetch.js`.

# 12. SQLite Event Store

## 12.1. `trace_events`

SQL

```
CREATE TABLE trace_events (
    event_id TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,

    schema_version INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'browser',
    event_type TEXT NOT NULL,

    timestamp_ns INTEGER NOT NULL,
    sequence INTEGER,

    page_id TEXT,
    frame_id TEXT,

    execution_id TEXT,
    parent_execution_id TEXT,

    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    payload_hash TEXT NOT NULL,
    ingested_at_ns INTEGER NOT NULL,

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

Index:

SQL

```
CREATE INDEX idx_trace_events_session_time
ON trace_events(session_id, timestamp_ns);

CREATE INDEX idx_trace_events_session_type
ON trace_events(session_id, event_type);

CREATE INDEX idx_trace_events_page
ON trace_events(session_id, page_id);

CREATE INDEX idx_trace_events_execution
ON trace_events(execution_id);

CREATE INDEX idx_trace_events_payload_hash
ON trace_events(payload_hash);
```

# 13. Network Tables

## 13.1. `network_requests`

SQL

```
CREATE TABLE network_requests (
    id TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    execution_id TEXT,

    page_id TEXT,
    frame_id TEXT,

    method TEXT NOT NULL,
    url TEXT NOT NULL,
    url_template TEXT,

    scheme TEXT,
    host TEXT,
    port INTEGER,
    path TEXT,

    query_json TEXT,
    headers_json TEXT,
    body_json TEXT,

    resource_type TEXT,
    initiator_type TEXT,

    started_at_ns INTEGER NOT NULL,
    completed_at_ns INTEGER,

    status TEXT NOT NULL DEFAULT 'pending',

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id),

    FOREIGN KEY (event_id)
        REFERENCES trace_events(event_id)
);
```

## 13.2. `network_responses`

SQL

```
CREATE TABLE network_responses (
    id TEXT PRIMARY KEY,

    request_id TEXT NOT NULL,
    event_id TEXT NOT NULL,

    status_code INTEGER,
    status_text TEXT,

    headers_json TEXT,
    body_json TEXT,

    content_type TEXT,
    body_size INTEGER,
    body_hash TEXT,

    received_at_ns INTEGER NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (request_id)
        REFERENCES network_requests(id),

    FOREIGN KEY (event_id)
        REFERENCES trace_events(event_id)
);
```

### Xử lý response body

Không phải response nào cũng là JSON:

```
application/json
text/html
text/plain
application/octet-stream
image/*
video/*
```

Nên có `body_storage_type`:

```
inline
file_reference
hash_only
unavailable
```

Ví dụ:

JSON

```
{
  "body_storage_type": "file_reference",
  "body_ref": "data/sessions/sess_01/payloads/body_001.bin",
  "body_hash": "sha256:...",
  "body_size": 5242880
}
```

Không nên nhét response binary lớn trực tiếp vào `payload_json`.

# 14. Function Execution Store

## 14.1. `function_executions`

SQL

```
CREATE TABLE function_executions (
    id TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,

    function_name TEXT,
    module_name TEXT,
    source_location_json TEXT,

    page_id TEXT,
    frame_id TEXT,

    parent_execution_id TEXT,

    started_at_ns INTEGER NOT NULL,
    ended_at_ns INTEGER,

    status TEXT NOT NULL,

    arguments_json TEXT,
    return_value_ref TEXT,
    exception_json TEXT,
    stack_trace TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id)
);
```

## 14.2. Vấn đề async JavaScript

Cần phân biệt:

```
function call
function return
promise resolve
promise reject
callback
```

Không phải mọi function call đều có thể liên kết trực tiếp với một network request.

Do đó:

* `execution_id` có thể null.

* `parent_execution_id` có thể không xác định.

* Stack trace có thể bị thiếu.

* Event ordering không đồng nghĩa với causal dependency.

# 15. Storage Operations

## 15.1. `storage_operations`

SQL

```
CREATE TABLE storage_operations (
    id TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    execution_id TEXT,

    page_id TEXT,
    frame_id TEXT,

    storage_type TEXT NOT NULL,
    storage_scope TEXT,

    storage_key TEXT NOT NULL,
    operation TEXT NOT NULL,

    value_ref TEXT,
    value_type TEXT,
    value_length INTEGER,

    timestamp_ns INTEGER NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (session_id)
        REFERENCES sessions(id),

    FOREIGN KEY (event_id)
        REFERENCES trace_events(event_id)
);
```

Giá trị `storage_type`:

```
local_storage
session_storage
cookie
indexed_db
```

Phase 1 có thể triển khai trước:

```
local_storage
session_storage
cookie
```

IndexedDB nên bổ sung sau vì có nhiều API bất đồng bộ và cấu trúc object phức tạp.

# 16. Value Observation

Để sau này phát hiện:

```
response.body.user_id
    ↓
function argument
    ↓
request.query.user_id
```

cần định danh value độc lập với nơi nó xuất hiện.

## 16.1. `value_observations`

SQL

```
CREATE TABLE value_observations (
    id TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,

    value_ref TEXT NOT NULL,
    value_hash TEXT NOT NULL,

    value_type TEXT NOT NULL,
    value_length INTEGER,

    json_path TEXT,
    variable_name TEXT,

    sensitivity TEXT NOT NULL DEFAULT 'unknown',

    redacted_value TEXT,

    first_seen_at_ns INTEGER NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

### Value reference

```
val_01
val_02
val_03
```

Một value có thể xuất hiện trong nhiều event. Không nên tạo value mới chỉ vì cùng một dữ liệu được quan sát ở một field khác.

Tuy nhiên, matching bằng hash cần xem xét:

* Primitive value phổ biến.

* Object normalization.

* Encoding khác nhau.

* String và byte array.

* Giá trị bị cắt.

* Giá trị đã được encode.

# 17. Redaction

File:

```
app/infrastructure/serialization/redaction.py
```

## 17.1. Các trường nhạy cảm

```
authorization
cookie
set-cookie
proxy-authorization
x-api-key
access_token
refresh_token
id_token
password
client_secret
```

Redaction cần áp dụng cho:

```
request headers
response headers
URL query
request body
response body
storage values
function arguments
function return values
console logs
```

## 17.2. Chính sách lưu trữ

JSON

```
{
  "value_ref": "val_01",
  "value_type": "string",
  "value_length": 64,
  "sensitivity": "secret",
  "display_value": "[REDACTED]",
  "match_token": "hmac-sha256:..."
}
```

Phân biệt:

```
raw value
display value
matching token
```

MCP không nên trả plaintext secret mặc định. `SecretStore` chỉ nên được tích hợp khi có use case và policy cụ thể.

# 18. Raw Event Archive

Cấu trúc thư mục:

```
data/
├── database/
│   └── lineage.db
└── sessions/
    └── <session_id>/
        ├── metadata.json
        ├── raw_events.jsonl
        ├── payloads/
        ├── screenshots/
        └── exports/
```

## 18.1. JSONL

JSON

```
{"event_id":"evt_01","event_type":"network_request","session_id":"sess_01","payload":{}}
{"event_id":"evt_02","event_type":"network_response","session_id":"sess_01","payload":{}}
```

JSONL nên được dùng cho:

* Debug.

* Export.

* Backup.

* Reprocessing.

* Điều tra event lỗi.

SQLite nên phục vụ:

* Query.

* Index.

* Timeline.

* Deduplication.

* Normalized entities.

## 18.2. Tránh mất dữ liệu

Một phương án đơn giản:

```
1. Persist event vào SQLite
2. Commit transaction
3. Append raw JSONL
4. Đánh dấu raw_archived = true
```

Nếu bước 3 thất bại, tạo retry job thay vì bỏ qua lỗi.

# 19. Queue và Backpressure

Browser có thể phát sinh rất nhiều event nếu instrumentation hook rộng.

```
Page / JS Bridge
       │
       ▼
Bounded Async Queue
       │
       ▼
Ingestion Worker
       │
       ▼
Batch SQLite Writer
```

## 19.1. Phân loại event khi quá tải

|
Event

|

Chính sách

|
| --- | --- |
|

Network request

|

Không drop mặc định

|
|

Network response

|

Không drop mặc định

|
|

Storage operation

|

Không drop mặc định

|
|

Crypto/serialization

|

Giữ khi được bật

|
|

Console log

|

Có thể sampling

|
|

Runtime error

|

Giữ

|
|

Function call

|

Có thể sampling có kiểm soát

|

Không nên drop event một cách âm thầm. Cần ghi thống kê:

JSON

```
{
  "dropped_events": 12,
  "dropped_by_type": {
    "console_log": 10,
    "function_call": 2
  }
}
```

# 20. MCP Tools của Phase 1

Chỉ nên expose các tool phục vụ capture và đọc dữ liệu.

## 20.1. `start_capture_session`

Input:

JSON

```
{
  "name": "login_flow",
  "target": "https://example.com",
  "headless": false,
  "capture_options": {
    "network": true,
    "runtime": true,
    "storage": true,
    "serialization": false,
    "screenshots": false
  }
}
```

Output:

JSON

```
{
  "session_id": "sess_01",
  "status": "starting",
  "source": "browser"
}
```

## 20.2. `get_capture_status`

Input:

JSON

```
{
  "session_id": "sess_01",
  "include_statistics": true
}
```

Output:

JSON

```
{
  "session_id": "sess_01",
  "status": "running",
  "statistics": {
    "total_events": 120,
    "network_requests": 20,
    "network_responses": 18,
    "storage_operations": 4,
    "runtime_errors": 0,
    "dropped_events": 0
  },
  "adapter": {
    "connected": true,
    "last_event_at_ns": 1726830050000000000
  }
}
```

## 20.3. `stop_capture_session`

Input:

JSON

```json
{
  "session_id": "sess_01",
  "save_storage_state": true
}
```

Output:

JSON

```json
{
  "session_id": "sess_01",
  "status": "stopped",
  "statistics": {
    "total_events": 120,
    "network_requests": 20,
    "network_responses": 18,
    "storage_operations": 4,
    "runtime_errors": 0,
    "dropped_events": 0
  },
  "duration_seconds": 15.4,
  "archive_paths": {
    "db": "data/database/lineage.db",
    "raw_events": "data/sessions/sess_01/raw_events.jsonl",
    "storage_state": "data/sessions/sess_01/storage_state.json"
  }
}
```

## 20.4. `list_capture_sessions`

Input:

JSON

```json
{
  "task_id": "task_fb_change_name",
  "status": "stopped",
  "limit": 20
}
```

Output:

JSON

```json
{
  "sessions": [
    {
      "id": "sess_01",
      "task_id": "task_fb_change_name",
      "name": "Session 1 - Rename An",
      "target": "https://example.com/settings",
      "status": "stopped",
      "created_at_ns": 1726830000000000000,
      "event_count": 120
    },
    {
      "id": "sess_02",
      "task_id": "task_fb_change_name",
      "name": "Session 2 - Rename Binh",
      "target": "https://example.com/settings",
      "status": "stopped",
      "created_at_ns": 1726830050000000000,
      "event_count": 115
    }
  ]
}
```

## 20.5. `get_session_events`

Input:

JSON

```json
{
  "session_id": "sess_01",
  "event_types": ["network_request", "storage_write"],
  "limit": 50,
  "offset": 0
}
```

Output:

JSON

```json
{
  "session_id": "sess_01",
  "total": 24,
  "events": [
    {
      "event_id": "evt_01",
      "event_type": "storage_write",
      "timestamp_ns": 1726830010000000000,
      "payload": {
        "storage_type": "local_storage",
        "operation": "write",
        "storage_key": "auth_token",
        "value_preview": "[REDACTED:sha256:...]"
      }
    }
  ]
}
```

## 20.6. `export_session_archive`

Input:

JSON

```json
{
  "session_id": "sess_01",
  "include_payloads": true,
  "export_format": "zip"
}
```

Output:

JSON

```json
{
  "session_id": "sess_01",
  "archive_file": "data/sessions/sess_01/export_sess_01.zip",
  "size_bytes": 1048576,
  "manifest": {
    "raw_events_count": 120,
    "payload_files_count": 8,
    "has_sqlite_snapshot": true
  }
}
```

# 21. Tiêu chí hoàn thành (Definition of Done - DoD)

Một triển khai Phase 1 được coi là hoàn tất khi đáp ứng đầy đủ các tiêu chuẩn định lượng và chất lượng sau:

1. **Schema & Migration toàn vẹn:**
   * Cơ sở dữ liệu SQLite thiết lập chuẩn với chế độ WAL (`PRAGMA journal_mode=WAL`) và bật kiểm tra khóa ngoại (`PRAGMA foreign_keys=ON`).
   * Toàn bộ các bảng cốt lõi (`sessions`, `trace_events`, `function_executions`, `network_requests`, `network_responses`, `storage_operations`) được quản lý bằng Alembic migration, có khả năng `upgrade` và `downgrade` sạch sẽ.
2. **Đảm bảo không mất mát dữ liệu (Zero Silent Drop):**
   * Mọi sự kiện mạng (`fetch`, `XHR`) và thao tác `storage` phát sinh từ trình duyệt đều phải được đưa vào Event Store mà không bị bỏ sót âm thầm.
   * Nếu xảy ra quá tải hàng đợi hoặc lỗi phân tích cú pháp, số lượng event bị drop phải được đếm và ghi nhận rõ ràng vào `sessions.metadata_json`.
3. **Bảo mật & Redaction tuyệt đối:**
   * Mọi trường nhạy cảm (`Authorization`, `Cookie`, `Set-Cookie`, `access_token`, mật khẩu) đều phải được che giấu bằng HMAC token hoặc hash trước khi lưu trữ xuống SQLite hoặc xuất qua MCP.
   * Tuyệt đối không lưu plaintext credentials trong `sessions.metadata_json` hay các trường log.
4. **Hỗ trợ Task Grouping & Pre-seed:**
   * Cho phép khởi tạo nhiều session (2-3 sessions) thuộc cùng một `task_id` phục vụ differential analysis.
   * Khởi động trình duyệt có khả năng tiêm trước Cookies và Storage State trước khi mã JavaScript của website mục tiêu được nạp.
5. **Dọn dẹp tiến trình & Quản lý tài nguyên:**
   * Quá trình dừng session (`stop_capture_session`) hoặc đóng trình duyệt thủ công phải giải phóng hoàn toàn tiến trình Chromium, không để lại zombie process.
   * Flush sạch bộ nhớ đệm sự kiện trước khi đóng kết nối DB.

# 22. Chiến lược kiểm thử (Testing Strategy)

Hệ thống Phase 1 được kiểm thử đa tầng để bảo đảm độ ổn định cao:

1. **Unit Testing:**
   * *JS Bridge Parser:* Kiểm tra khả năng serialize/deserialize JSON an toàn, chống đệ quy vô hạn khi hook `JSON.stringify`.
   * *Redaction Engine:* Kiểm thử độ che giấu các header `Authorization`, token query parameters, và cookie sensitive keys.
   * *Event Normalizer:* Kiểm tra tính toán `payload_hash`, trích xuất host/path từ URL.
2. **Integration Testing:**
   * *SQLite Repository:* Kiểm thử chèn dữ liệu đồng thời, kiểm tra ràng buộc khóa ngoại giữa `trace_events` và các bảng thực thể con (`network_requests`, `storage_operations`), cơ chế upsert placeholder.
   * *Alembic Migration:* Chạy migration trên SQLite DB mẫu trong môi trường CI/CD.
3. **End-to-End (E2E) Browser Capture Test:**
   * Khởi chạy mock server cục bộ với `ThreadingHTTPServer`.
   * Khởi động `StartSessionUseCase` với Pre-seeded state (Cookie + localStorage).
   * Điều hướng trình duyệt Playwright, thực hiện thao tác gọi API POST có kèm header Authorization.
   * Dừng session và kiểm tra:
     * Dữ liệu trong `sessions` và `trace_events` đầy đủ.
     * Header Authorization đã được che giấu.
     * Task grouping liên kết chính xác giữa các session khác nhau.

# 23. Bàn giao sang Phase 2 (Handover to Phase 2: Graph Projection)

Phase 1 đóng vai trò là nền móng thu thập dữ liệu (Data Acquisition). Sau khi hoàn thành, Phase 1 bàn giao cho Phase 2 (Graph Projection) hợp đồng dữ liệu sau:

1. **Hợp đồng Event Store (SQLite & JSONL):**
   * Bảng `trace_events`: Cung cấp dòng thời gian tuần tự (`timestamp_ns`, `sequence`) của mọi hoạt động client-side.
   * Bảng `network_requests` & `network_responses`: Đã được trích xuất sẵn `method`, `url`, `headers_json`, `body_json` và liên kết với `request_id`.
   * Bảng `storage_operations`: Đã phân loại `local_storage`, `session_storage`, `cookie` kèm các thao tác `read`, `write`, `delete`.
   * Bảng `sessions`: Cung cấp `task_id` và danh sách các session tham gia phân tích vi phân.
2. **Đầu vào cho Graph Projection Engine:**
   * Phase 2 sẽ đọc trực tiếp từ SQLite theo từng batch sự kiện của một `session_id`.
   * Chuyển đổi các thực thể thành `graph_nodes` (Node Request, Node Function, Node Storage, Node Value).
   * Tạo các `graph_edges` nối giữa các node dựa trên bằng chứng dữ liệu (`produces`, `consumed_by`, `transforms_into`) và ghi nhận vào bảng `edge_evidence`.
3. **Phân tích so sánh đa phiên (Differential Analysis):**
   * Nhờ có `task_id` được Phase 1 gán cho từng session, Phase 2 có thể song song chiếu đồ thị cho Session A và Session B, tạo tiền đề để đối chiếu và tự động suy luận ra đâu là dynamic token, đâu là static signature phục vụ Phase 3 Replay Engine.

