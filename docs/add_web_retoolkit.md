
# Phân Tích Chuyên Sâu 7 Giai Đoạn `web-re-toolkit` & Kế Hoạch Tích Hợp Vào `mcp_serve_reverse`

---

## PHẦN 1: BẢN CHẤT KỸ THUẬT CỦA 7 GIAI ĐOẠN TRONG `web-re-toolkit`

Kho mã nguồn [web-re-toolkit](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit) là một bộ công cụ dịch ngược (Reverse Engineering) hiện đại viết bằng **Rust (25 crates)**, chuyên trị các hệ thống phòng thủ bot hàng đầu thế giới (Akamai Bot Manager V2/V3, Kasada Interrogation, Cloudflare Turnstile, Datadome, Shape Security).

```
   ┌────────────────────────────────────────────────────────────────────────────────────────┐
   │                               7 GIAI ĐOẠN DỊCH NGƯỢC NÂNG CAO                          │
   ├──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬─────────────┴─────────────┐
   │ GIAI ĐOẠN 1  │ GIAI ĐOẠN 2  │ GIAI ĐOẠN 3  │ GIAI ĐOẠN 4  │ GIAI ĐOẠN 5  │ GIAI ĐOẠN 6 │ GIAI ĐOẠN 7 │
   │ Capture &    │ AST          │ VM Lifting   │ Crypto &     │ V8 Live      │ Anti-Detect │ Headless    │
   │ Probing      │ Deobfuscate  │ (Bytecode)   │ Wire Codecs  │ Mounting     │ & Drift     │ Client SDK  │
   └──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴─────────────┴─────────────┘
```

---

### GIAI ĐOẠN 1: Thu Thập Dữ Liệu & Giám Sát Runtime (Capture & Probing)
- **Các Crate lõi**: [`wre-cdp`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-cdp), [`wre-probe`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-probe), [`wre-capture`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-capture), [`wre-behavior`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-behavior).
- **Cơ chế kỹ thuật**:
  1. **CDP thô (Chrome DevTools Protocol over WebSocket)**: Thay vì dùng Puppeteer hay Selenium (dễ bị phát hiện qua cờ `navigator.webdriver` hoặc rò rỉ runtime), `wre-cdp` kết nối trực tiếp qua WebSocket vào socket debug của Chrome. Hỗ trợ Fetch-based script interception để thay thế/chèn mã trước khi browser parse script.
  2. **In-Page Probing**: `wre-probe` tiêm (inject) một script can thiệp vào `Page.addScriptToEvaluateOnNewDocument`. Script này đặt bẫy Proxy/getter trên: `window`, `document`, `navigator`, `prototype`, `String.prototype.charCodeAt`, `crypto.subtle`, `HTMLCanvasElement.toDataURL`, `WebGLRenderingContext`.
  3. **Capture Bundle chuẩn hóa**: `wre-capture` đóng gói toàn bộ HTTP archive, biến thiên DOM, các file script tải về và trace log của probe thành thư mục `captures/<target-name>/`.
  4. **Giả lập vi phân hành vi (`wre-behavior`)**: Di chuyển chuột theo đường cong Bezier bậc 3, mô phỏng lực nhấn, gia tốc phím và độ trễ ngẫu nhiên (không dùng hàm sleep hằng số) nhằm đánh lừa AI phân tích hành vi của Akamai/Cloudflare.

---

### GIAI ĐOẠN 2: Giải Mã & Tái Cấu Trúc Javascript (AST Deobfuscation)
- **Crate lõi**: [`wre-js`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-js).
- **Cơ chế kỹ thuật**:
  1. **26-Pass Oxc AST Pipeline**: Dựa trên parser siêu tốc [Oxc](https://github.com/oxc-project/oxc) của Rust. Chạy lặp 26 lượt tối ưu cho đến khi đạt điểm dừng không đổi (**fixpoint**):
     - **Control Flow Unflattening**: Dựng lại đồ thị luồng điều khiển từ các vòng lặp `switch(state)` khổng lồ đặc trưng của Obfuscator.io / JSFuck.
     - **Constant Folding & Dead-Code Elimination**: Tính toán trước các biểu thức toán học tĩnh (`1 ^ 45 + 3`), bóc tách mảng chuỗi mã hóa và xóa toàn bộ các khối lệnh không bao giờ chạm tới.
     - **Contextual Renaming**: Đổi tên biến rác (`_0x4a1b`) thành các tên có nghĩa dựa trên ngữ cảnh gọi API.
  2. **Surface Indexer**: Quét AST để lập chỉ mục danh sách mọi thuộc tính nhạy cảm mà một hàm đọc (ví dụ: hàm `a()` đọc `navigator.userAgent`, `screen.colorDepth`, `localStorage.getItem`).
  3. **Self-Integrity & Re-sign**: Các script chống dịch ngược (Anti-Tamper) thường có hàm kiểm tra `Function.prototype.toString()` hoặc hash mã nguồn của chính nó. `wre-js` phân tích cơ chế hash và tự động tính toán lại giá trị hash sau khi ta chèn code phân tích (patch/hook), ngăn script tự hủy (crash).
  4. **Equivalence Gate**: So sánh ngữ nghĩa AST trước và sau khi deobfuscate, đảm bảo script sau khi làm sạch không làm mất bất kỳ logic nghiệp vụ nào của bản gốc.

---

### GIAI ĐOẠN 3: Bẻ Khóa Máy Ảo JS (VM De-virtualization & Bytecode Lifting)
- **Crate lõi**: [`wre-vm`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-vm).
- **Đối tượng**: Chuyên trị các hệ thống bảo mật cấp cao (Kasada, Datadome, Shape) - nơi toàn bộ logic chống bot được biên dịch thành bytecode nhị phân tùy biến và thực thi qua một máy ảo JS riêng.
- **Cơ chế kỹ thuật**:
  1. **VM Discovery**: Tự động tìm kiếm vòng lặp phân phối lệnh (`dispatch loop`: `while(true) switch(opcode)`) và bảng con trỏ hàm (`handler table`).
  2. **Concolic Probe**: Kết hợp thực thi cụ thể (concrete) và ký hiệu (symbolic) lên từng opcode handler để tự động phân loại cấu trúc thanh ghi, con trỏ ngăn xếp và khuôn mẫu toán hạng.
  3. **Bytecode Lifting**: Khôi phục Control Flow Graph (CFG) của bytecode nhị phân và nâng cấp (**lift**) toàn bộ luồng nhị phân đó ngược trở lại thành mã nguồn JavaScript chuẩn có thể đọc và phân tích được.

---

### GIAI ĐOẠN 4: Phân Tích Mật Mã Học & Codec Dữ Liệu Dây (Crypto & Wire)
- **Các Crate lõi**: [`wre-crypto`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-crypto), [`wre-pack`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-pack), [`wre-pow`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-pow), [`wre-wire`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-wire).
- **Cơ chế kỹ thuật**:
  1. **Nhận diện & Bẻ khóa Crypto**: Thư viện thuật toán đối xứng (XTEA, TEA, AES, RC4), các dạng Checksum/Hash (Murmur3, FNV1a, CRC32, XorSum) và thuật toán khôi phục khóa XOR lặp (`repeating key recovery`).
  2. **Custom Base-N & Variable Radix (`wre-pack`)**: Tự động nhận diện các bảng mã Base64 bị tráo đổi thứ tự ký tự (custom alphabet) hoặc hệ cơ số biến thiên.
  3. **Động cơ PoW đa luồng (`wre-pow`)**: Tận dụng CPU đa luồng của Rust để giải các bài toán Proof-of-Work (chuỗi hash SHA256/Murmur có $N$ số 0 dẫn đầu) của Akamai Pixel hay Altcha trong **vài mili-giây**.
  4. **Payload Decoding & Diffing (`wre-wire`)**: Mở các tầng payload lồng nhau (`Gzip -> XOR -> Base64 -> JSON`). So sánh vi phân theo địa chỉ trường (`address path diff`) và cung cấp kỹ thuật **Donor Forging** (lấy một payload thật làm "vật hiến tặng" rồi chỉ thay đổi các trường biến thiên cần thiết).

---

### GIAI ĐOẠN 5: V8 Sandbox & Cơ Chế "Mượn Hàm" Trực Tiếp (V8 Live Mounting)
- **Các Crate lõi**: [`wre-live`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-live), [`wre-sandbox`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-sandbox), [`wre-env`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-env).
- **Triết lý cốt lõi**: **"Borrow, do not reimplement" (Hãy mượn, đừng viết lại)**.
- **Cơ chế kỹ thuật**:
  - Không cần mất hàng tuần dịch ngược thuật toán mã hóa phức tạp sang Python/Rust.
  - Nhúng trực tiếp Google V8 Engine bằng C++ bindings trong Rust.
  - Nạp thẳng file JS của mục tiêu vào V8 Realm.
  - [`wre-sandbox`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-sandbox) cung cấp một lớp giả lập môi trường trình duyệt ở tầng native V8 C++ (không phải JSDOM cồng kềnh, không phải Chrome tốn hàng GB RAM). Nó nạp profile thiết bị thật (iPhone, Windows Chrome) và bắt trọn đồ thị đối tượng (`wre-env`).
  - Lệnh `wre mount` định vị hàm mã hóa/ký của đối phương (ví dụ hàm `encrypt_telemetry()`) và gọi trực tiếp nó từ bên ngoài để sinh ra token hợp lệ 100%!

---

### GIAI ĐOẠN 6: Chống Phát Hiện & Đồng Bộ Đa Phiên Bản (Anti-Detect & Drift)
- **Các Crate lõi**: [`wre-ident`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-ident), [`wre-net`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-net), [`wre-oracle`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-oracle), [`wre-variants`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-variants).
- **Cơ chế kỹ thuật**:
  1. **Kháng Drift (AST Shape Hashing)**:
     - Khi website cập nhật phiên bản mới, tên hàm và biến bị đổi ngẫu nhiên (`a` thành `b9`).
     - `wre-ident` tạo mã băm hình thái cú pháp (**AST Shape Hash**) độc lập với tên biến. Khóa liên kết được lưu vào `targets/<name>.lock`.
     - Khi chạy `wre drift`, hệ thống tự động so khớp cấu trúc và chỉ ra: *"Hàm mã hóa ở build cũ giờ là hàm `xyz` ở build mới"*, giúp tool tiếp tục hoạt động mà không cần can thiệp thủ công.
  2. **Vân tay mạng chân thực (`wre-net`)**:
     - Tùy biến bộ bắt tay TLS (ClientHello, thứ tự Cipher Suite, Extension, JA3/JA4) và HTTP/2 (SETTINGS frames, thứ tự Pseudo-Headers, Window Size, HPACK).
     - Giúp request gửi từ terminal/server có vân tay mạng giống 100% Google Chrome thật trên Windows/macOS.
  3. **Quét dấu vết tự động hóa (`wre-variants`)**: Kiểm tra 64 dấu vết bot (automation markers) và cả các dấu vết do việc cố tình che giấu để lại (concealment tells).

---

### GIAI ĐOẠN 7: Đóng Gói Client Headless Tự Động (Codegen & Packaging)
- **Các Crate lõi**: [`wre-client`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-client), [`wre-clientd`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-clientd), [`wre-codegen`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-codegen).
- **Cơ chế kỹ thuật**:
  1. **Sidecar Daemon (`wred`)**: Chạy V8 solver ngầm, giao tiếp với ứng dụng crawler/backend qua IPC binary socket (hoặc Named Pipe trên Windows) với độ trễ dưới 1ms.
  2. **Codegen ra 4 ngôn ngữ**: `wre-codegen` tự động biên dịch solver thành các thư viện SDK hoàn chỉnh: **Python (Wheel)**, **Node.js (NPM)**, **Go**, và **Rust**.

---

## PHẦN 2: ĐỐI CHIẾU VỚI HIỆN TRẠNG `mcp_serve_reverse`

| Hạng mục năng lực | Dự án hiện tại (`mcp_serve_reverse`) | Dự án `web-re-toolkit` (Rust Core) | Cơ hội đột phá khi kết hợp |
| :--- | :--- | :--- | :--- |
| **Giao diện & Trải nghiệm Agent** | Đã có **MCP Server chuẩn**, REST API Starlette, **Playground Studio Graph UI**. Agent có thể gọi tool trực tiếp. | Chủ yếu là CLI (`wre ...`), chưa có MCP Server hay UI trực quan. | Biến sức mạnh của `web-re-toolkit` thành **MCP Tools** để AI Agent điều khiển tự động qua hội thoại. |
| **Thu thập dữ liệu (Capture)** | Playwright / CloakBrowser bắt HTTP Events & DOM cơ bản, lưu SQLite. | `wre-cdp` kết nối trực tiếp WebSocket CDP, tiêm probe bẫy Crypto, WebGL, Canvas, hành vi Bezier. | Nâng cấp bộ bắt của `mcp_serve_reverse` không chỉ bắt mạng mà còn bắt được toàn bộ **Crypto/Canvas/Telemetry Probing Events**. |
| **Phân tích mã nguồn JS** | **Chưa có**: Chỉ nhìn thấy URL file `.js`, coi logic JS bên trong là "hộp đen". | Bộ deobfuscate 26-pass Oxc AST, Surface Indexer, Unflattening, Integrity Re-sign. | AI Agent có thể gọi `deobfuscate_script` và `inspect_js_surface` để đọc hiểu và phân tích thuật toán chống bot. |
| **Máy ảo JS (VM Reverse)** | **Chưa có**. | Tự động dò `dispatch loop`, concolic probing và lift bytecode thành JS thông thường. | Giải quyết các mục tiêu bảo vệ tầng cao (Kasada, Datadome, Shape). |
| **Tính toán Token / Payload** | Phải viết lại thuật toán bằng Python (ví dụ: bóc tách `fb_dtsg`, tính `jazoest` trong `fb_rename_cookie.py`). | **V8 Live Mounting**: Nạp thẳng file JS vào V8 Sandbox và gọi trực tiếp hàm mã hóa của đối phương. | Giảm thời gian reverse từ **hàng tuần xuống vài phút**, không cần tái cài đặt thuật toán crypto phức tạp. |
| **Phân tích Payload Dây** | Đã có `differential_analysis` (phân loại STATIC/DYNAMIC/HASH), `blob_storage` (`puremagic`). | `wre-wire` bóc tách sâu đa tầng codec (`XOR+Base64+Gzip`), diff theo địa chỉ trường, Donor Forging. | Cho phép cấy ghép tham số tự động (`wire_forge`) mà không cần giải mã 100% các trường ẩn. |
| **Chống Drift khi Web cập nhật** | **Dễ gãy**: Nếu web đổi DocID hoặc logic biến, kịch bản Python phải viết lại thủ công. | `wre-ident` đánh hash hình thái cú pháp (**AST Shape Hashing**), tự động map hàm cũ sang hàm mới qua lockfile. | Kịch bản replay và tool MCP có khả năng **tự sửa chữa (self-healing)** khi website đích đẩy bản build mới. |
| **Vân tay mạng (TLS/H2)** | Dùng `httpx` (mang vân tay OpenSSL Python, dễ bị Cloudflare/Akamai chặn). | `wre-net` giả lập 100% JA3/JA4 TLS ClientHello và Akamai HTTP/2 frame order. | Gửi request replay mà không bao giờ bị Cloudflare/Akamai gắn cờ bot. |

---

## PHẦN 3: KẾ HOẠCH NÂNG CẤP DỰ ÁN THÀNH "UNIVERSAL REVERSE ENGINEERING MCP"

### 1. Kiến Trúc Tích Hợp (Architecture Bridge)

Tận dụng kiến trúc Clean Architecture sẵn có trong `app/`:
```
   AI AGENT (Antigravity IDE / Claude Desktop / Cursor)
                        │
                        ▼ (MCP Protocol - stdio / SSE)
         ┌──────────────────────────────┐
         │      app/interfaces/mcp/     │
         │   (MCP Server & Tool Router) │
         └──────────────┬───────────────┘
                        │
                        ▼ (Application Use Cases)
         ┌──────────────────────────────┐
         │       app/application/       │
         │   - js_analysis/             │
         │   - v8_runtime/              │
         │   - wire_codecs/             │
         │   - drift_sync/              │
         └──────────────┬───────────────┘
                        │
                        ▼ (Adapters Layer)
         ┌────────────────────────────────────────────────────────┐
         │                 app/adapters/toolkit/                  │
         │  WreCliAdapter / WreDaemonBridge (Subprocess / IPC)   │
         └────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼ (CLI JSON Flag: wre --json ...)
         ┌────────────────────────────────────────────────────────┐
         │             web-re-toolkit (Rust Binary)               │
         │   wre-js · wre-vm · wre-live · wre-wire · wre-ident    │
         └────────────────────────────────────────────────────────┘
```

> [!TIP]
> Tất cả các lệnh của CLI `wre` đều hỗ trợ cờ toàn cục `--json` (được định nghĩa trong [`Context::emit`](file:///d:/source_code/mcp_serve_reverse/web-re-toolkit/crates/wre-cli/src/main.rs#L26-L38)). Adapter Python có thể gọi các lệnh này bất đồng bộ qua `asyncio.create_subprocess_exec` và nhận về JSON có cấu trúc đầy đủ mà không cần phụ thuộc phức tạp vào C-ABI.

---

### 2. Danh Mục 8 MCP Tools Mới Cần Bổ Sung Cho Agent

#### Nhóm 1: AST Deobfuscation & Phân Tích Bề Mặt JS (Giai đoạn 2)
1. **`deobfuscate_javascript`**:
   - **Đầu vào**: `script_content` hoặc `file_path`.
   - **Chức năng**: Gọi `wre deobf` chạy pipeline 26-pass (Control flow unflattening, gập hằng số, đổi tên biến).
   - **Đầu ra**: File mã nguồn sạch, dễ đọc kèm báo cáo thống kê các pass đã thực hiện.
2. **`inspect_js_surface`**:
   - **Đầu vào**: `file_path`.
   - **Chức năng**: Gọi `wre surface` để báo cáo danh sách tất cả các biến môi trường trình duyệt (`navigator`, `screen`, `cookie`, `canvas`) mà các hàm trong script đang thu thập.

#### Nhóm 2: Bẻ Khóa Máy Ảo JS (Giai đoạn 3)
3. **`lift_vm_bytecode`**:
   - **Đầu vào**: `script_path`.
   - **Chức năng**: Tự động phát hiện dispatch loop (`wre vm discover`), phân tích opcodes (`wre vm probe`) và nâng cấp bytecode thành mã nguồn JavaScript tường minh (`wre vm lift`).

#### Nhóm 3: V8 Sandbox & "Mượn Hàm" Không Cần Viết Lại (Giai đoạn 5 - Vũ khí tối thượng)
4. **`v8_mount_and_execute`**:
   - **Đầu vào**: `script_path`, `role` (ví dụ: `sign`, `encrypt`, `seal`), `args` (JSON array).
   - **Chức năng**: Gọi `wre mount` nạp script mục tiêu vào V8 Sandbox native, gọi trực tiếp hàm mã hóa của website và trả về token kết quả trong **1 mili-giây**.
   - **Ứng dụng thực tế**: Không cần reverse thủ công thuật toán sinh token của Facebook/Akamai, chỉ cần chỉ định hàm và truyền tham số đầu vào.

#### Nhóm 4: Bóc Tách & Cấy Ghép Payload Dây (Giai đoạn 4)
5. **`infer_wire_schema`**:
   - **Đầu vào**: Danh sách các request payloads bắt được.
   - **Chức năng**: Gọi `wre wire schema` để tự động bóc tách các tầng nén/mã hóa (`Gzip + Base64 + XOR`) và suy diễn lược đồ biến động của từng trường.
6. **`forge_wire_payload`**:
   - **Đầu vào**: `donor_payload_path`, danh sách `overrides` (`path=value`).
   - **Chức năng**: Cấy ghép các trường mong muốn vào payload mẫu thật của trình duyệt mà không làm hỏng tính toàn vẹn của các trường bảo mật ẩn khác.

#### Nhóm 5: Kháng Drift Đa Phiên Bản (Giai đoạn 6)
7. **`track_target_drift`**:
   - **Đầu vào**: `target_name`, `new_script_path`.
   - **Chức năng**: So sánh mã băm hình thái cú pháp (**AST Shape Hash**) trong file `.lock` với bản build mới của website (`wre drift`), tự động cập nhật lại vị trí các hàm cần thiết khi website đổi tên biến.

#### Nhóm 6: Đóng Gói Tự Động Client (Giai đoạn 7)
8. **`export_headless_client`**:
   - **Đầu vào**: `target_name`, ngôn ngữ xuất (`python`, `nodejs`, `go`).
   - **Chức năng**: Gọi `wre-codegen` để xuất ra một thư viện SDK độc lập kèm V8 Sidecar Daemon, chạy giải pháp với tốc độ tối đa mà không cần trình duyệt.

---

## PHẦN 4: LỘ TRÌNH THỰC HIỆN ĐỀ XUẤT

```
   BƯỚC 1: Build Core Rust (`wre`) ──► BƯỚC 2: Xây dựng Adapter Python ──► BƯỚC 3: Đăng ký MCP Tools & Phơi ra UI
```

1. **Bước 1 (Build Core Binary)**:
   - Chạy `cargo build --release` trong thư mục `web-re-toolkit` để tạo ra file thực thi nhị phân `wre.exe` (hoặc `wre`).
2. **Bước 2 (Viết Adapter tầng Infrastructure)**:
   - Tạo `app/adapters/toolkit/wre_adapter.py`: Wrapper wrapper async gọi `wre --json <command>` và parse output thành Pydantic models.
3. **Bước 3 (Đăng ký MCP Tools)**:
   - Tạo file `app/interfaces/mcp/tools/toolkit_tools.py` tích hợp 8 tools trên vào `Server` của MCP.
4. **Bước 4 (Tích hợp vào Playground Studio)**:
   - Bổ sung nút thao tác trên UI: **"Deobfuscate Script"**, **"V8 Live Mount"**, và **"Check Build Drift"** trực tiếp trên đồ thị Property Graph của từng phiên làm việc.

> [!IMPORTANT]
> Sự kết hợp giữa **Nền tảng Property Graph & Replay hiện có** của `mcp_serve_reverse` với **Động cơ phân tích AST & V8 Live Sandbox** của `web-re-toolkit` sẽ đưa bộ công cụ này lên vị thế hàng đầu trong lĩnh vực dịch ngược web tự động hóa bằng AI Agent.