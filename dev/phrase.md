Xác định các source
User event: click, input, submit
Network response
location, storage, DOM...
Đây là các node đầu vào của graph.
Xác định các sink quan trọng
fetch()
XMLHttpRequest.send()
WebSocket.send()
DOM mutation
postMessage()
Các API quan trọng khác.
Capture network bằng CDP
Network.requestWillBeSent
Network.responseReceived
Network.loadingFinished
Lấy requestId, URL, method, headers, body, initiator... CDP Network domain đã cung cấp trực tiếp các thông tin request/response này.
Capture execution context
Dùng CDP Debugger/Runtime.
Khi request được tạo, lấy call stack hiện tại.
Đồng thời bật async call stack tracking để không mất context qua Promise/async.

Instrument các boundary quan trọng

Không trace mọi function call. Chỉ hook:

fetch
XHR
WebSocket
Promise
Response.json/text/...
EventTarget
DOM mutation
postMessage

Đây là điểm cân bằng tốt giữa thông tin và overhead.

Correlate các event thành data-flow

Ví dụ:

click
  ↓
login()
  ↓
buildPayload()
  ↓
fetch()
  ↓
Request #42
  ↓
Response #42
  ↓
response.json()
  ↓
Promise continuation
  ↓
renderUser()

Đây chính là tư tưởng dynamic taint/data-flow analysis: theo dõi dữ liệu từ source qua các phép biến đổi đến sink. CodeQL cũng mô hình hóa flow qua variables, function calls, properties, arrays và promises.

Xây causal graph

Node:

ACTION
FUNCTION
VALUE
REQUEST
RESPONSE
PROMISE
DOM

Edge:

CALLS
CREATES
PASSES
SENDS
RESPONDS_TO
RESOLVES_TO
CONSUMES
UPDATES

Ví dụ:

[click]
   │
   ▼
[login()]
   │ CALLS
   ▼
[fetch()]
   │ CREATES
   ▼
[Request #42]
   │
   │ RESPONDS_TO
   ▼
[Response #42]
   │ CONSUMES
   ▼
[response.json()]
   │
   ▼
[Promise #7]
   │
   ▼
[renderUser()]
   │
   ▼
[DOM]