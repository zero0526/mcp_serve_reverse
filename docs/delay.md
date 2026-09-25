
Điểm nghẽn 1: Tư duy Single-Shot Replay (synthesize_code chỉ nhìn 1 Request đơn lẻ)
Vấn đề: synthesize_code chỉ sinh code cho duy nhất 1 request (useFXIMUpdateNameMutation). Nó hoàn toàn bỏ qua ngữ cảnh nghiệp vụ: request đổi tên bị Facebook chặn bởi Secured Action (Code 2136001), kích hoạt chuỗi 3 request tiếp theo (TwoStepVerificationRootQuery $\rightarrow$ useTwoStepVerificationSendCodeMutation $\rightarrow$ useTwoFactorLoginValidateCodeMutation $\rightarrow$ gửi lại mutation lần 2).
Hậu quả: Script sinh ra ban đầu không thể chạy thành công trên tài khoản có 2FA, buộc Agent phải tự query DB SQLite để chắp vá luồng 2FA thủ công.

Tool mới đề xuất: synthesize_workflow (Sinh kịch bản Replay theo chuỗi nghiệp vụ)
Thay vì chỉ sinh replay cho 1 request đơn lẻ, tool này nhận diện một Transaction Workflow (ví dụ: Bước 1: Validate $\rightarrow$ Bước 2: Request đổi tên $\rightarrow$ Bước 3: Nếu dính 2FA thì dispatch OTP $\rightarrow$ Bước 4: Validate OTP $\rightarrow$ Bước 5: Re-submit).
Tự động sinh ra cấu trúc code Python có xử lý rẽ nhánh if secured_action: handle_2fa().

---



Điểm nghẽn 4: Payload Media (Video, Ảnh, Base64, Binary lớn) làm tràn Context Token và Database [ĐÃ XỬ LÝ - RESOLVED]
- Vấn đề: Các endpoint làm việc với upload/tải video, hình ảnh thường chứa các attribute payload khổng lồ (chuỗi Base64 Data URI hàng trăm KB/MB, chuỗi nhị phân multipart chunks, byte array). Nếu đưa trực tiếp toàn bộ dữ liệu này vào SQLite database hoặc MCP Response, Agent sẽ cạn Context Token ngay lập tức, đồng thời gây lag và nguy cơ OOM.
- Giải pháp đã triển khai:
  1. Xây dựng engine [blob_storage.py](file:///data/projects/web-apps/cli/mcp_server_reverse/app/infrastructure/storage/blob_storage.py):
     - Tự động phát hiện Magic Bytes cho các định dạng: JPEG, PNG, GIF, WEBP, MP4, WebM, MP3, WAV, PDF, ZIP, GZIP.
     - Tự động phát hiện chuỗi Data URI Base64 (`data:image/...;base64,...`) và Raw Base64 media lớn.
     - Tự động cách ly (offload) nội dung nhị phân/media ra file vật lý lưu tại `data/blobs/{session_id}/blob_{sha256}.{ext}`.
     - Hỗ trợ chống trùng lặp (SHA-256 deduplication) để tiết kiệm dung lượng ổ đĩa.
     - Thay thế attribute bằng đối tượng tham chiếu `$blob_ref` gọn nhẹ (`file_path`, `mime_type`, `size_bytes`, `sha256`, `preview`).
  2. Tích hợp sâu vào quy trình xử lý:
     - [SQLiteEventRepository](file:///data/projects/web-apps/cli/mcp_server_reverse/app/adapters/persistence/sqlite/event_repository.py): Tự động tách media ngay khi ingest request/response, bảo vệ SQLite database luôn gọn gàng.
     - [SummarizeRequestUseCase](file:///data/projects/web-apps/cli/mcp_server_reverse/app/application/network/summarize_request.py): Tự động tách media trước khi trả về tóm tắt HTTP cho Agent.
     - [Request MCP Resource](file:///data/projects/web-apps/cli/mcp_server_reverse/app/interfaces/mcp/resources/request_resource.py): `request://{session_id}/{request_id}` chỉ hiển thị `$blob_ref` và preview.
  3. Tool MCP mới: `get_blob_content` ([server.py](file:///data/projects/web-apps/cli/mcp_server_reverse/app/interfaces/mcp/server.py#L473)):
     - Khi Agent hoặc script Replay cần kéo dữ liệu ra:
       * `format="summary"`: Xem thông số kích thước, MIME type, hash SHA-256 và preview hex.
       * `format="path"`: Lấy đường dẫn file tuyệt đối để truyền trực tiếp cho script Python (`requests.post(..., files={'video': open(path, 'rb')})`).
       * `format="base64"`: Kéo chuỗi Base64 với cơ chế phân đoạn (offset + max_bytes) tránh tràn token.
       * `format="text"`: Đọc văn bản UTF-8 nếu là payload text lớn.
  4. Kiểm thử tự động: Bổ sung 5 unit tests tại [test_blob_storage_and_media_offload.py](file:///data/projects/web-apps/cli/mcp_server_reverse/tests/test_blob_storage_and_media_offload.py) - Tất cả PASSED 100%.

---






GIAI ĐOẠN 1: Thu Thập Dữ Liệu & Giám Sát Runtime (Capture & Probing)
Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-cdp	wre browser	Quản lý vòng đời Chrome qua WebSocket CDP thô. Tái sử dụng instance, hỗ trợ Fetch-based script interception và đặt breakpoint theo pattern.	Kiểm soát hoàn toàn trình duyệt ở tầng giao thức DevTools mà không bị phát hiện như Puppeteer/Selenium.
wre-probe	(Tự động inject)	Sinh mã script can thiệp (instrumentation) khai báo sẵn: bẫy window, document, prototype, charCodeAt, WebCrypto, canvas, WebGL.	Phát hiện chính xác thời điểm các hàm tính toán mã hóa hoặc đọc vân tay phần cứng được kích hoạt.
wre-capture	wre capture	Điều khiển phiên duyệt web, trích xuất đồng thời: HTTP archive, DOM mutation, scripts nạp vào và log từ probe thành một capture bundle.	Gom toàn bộ dữ liệu phiên làm việc về một thư mục chuẩn hóa (captures/<name>).
wre-behavior	(Thư viện)	Giả lập chuỗi tọa độ chuột theo đường cong Bezier tự nhiên, mô phỏng lực nhấn, gia tốc phím và độ trễ ngẫu nhiên (không dùng hằng số cố định).	Vượt qua các bộ kiểm tra hành vi người dùng (User Behavioral Biometrics) của Cloudflare/Akamai/Kasada.
GIAI ĐOẠN 2: Giải Mã & Tái Cấu Trúc Javascript (AST Deobfuscation)
Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-js (Deobfuscator)	wre deobf	Bộ giải mã 26-pass trên nền Oxc AST: chạy lặp đến điểm dừng (fixpoint) gồm tháo phẳng luồng điều khiển (Control Flow Unflattening), gập hằng số, xóa dead-code, đổi tên biến theo ngữ cảnh.	Biến đổi file script JS bị obfuscate nặng nề (JSFuck, Obfuscator.io, Webpack mangled) thành code đọc hiểu được.
wre-js (Surface Indexer)	wre surface	Quét AST để lập chỉ mục tất cả các thuộc tính của trình duyệt (navigator, screen, cookie, localStorage) mà một hàm có thể chạm tới.	Trả lời ngay câu hỏi: “Hàm này đang thu thập dữ liệu gì từ máy tính người dùng?” mà không cần đọc từng dòng.
wre-js (Integrity & Resign)	wre integrity	Phân tích cơ chế tự kiểm tra hash mã nguồn của script (Self-Integrity Check) và tự động tính toán lại mã hash mới để ký lại sau khi vá code (patch).	Chống sập script khi chèn console.log hoặc hook sửa logic trong các script có cơ chế chống sửa đổi (Anti-Tamper).
wre-js (Equivalence Gate)	wre equivalent	So sánh tính tương đương ngữ nghĩa: đảm bảo script sau khi giải mã không truy cập thêm bất kỳ API nào nằm ngoài script gốc.	Đảm bảo an toàn 100% không làm sai lệch logic mã nguồn sau bước deobfuscate.
GIAI ĐOẠN 3: Bẻ Khóa Máy Ảo JS (VM De-virtualization & Bytecode Lifting)
Áp dụng cho các giải pháp bảo mật nâng cao mã hóa code thành bytecode tùy biến chạy qua hàm switch-case ảo (như Kasada, Datadome, Shape).

Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-vm (Discover)	wre vm discover	Quét AST nhận diện vòng lặp phân phối lệnh (dispatch loop) và mảng bảng hàm thực thi (handler table).	Tìm ra kiến trúc của máy ảo JS tùy biến trong script.
wre-vm (Concolic Probe)	wre vm probe	Thử nghiệm concolic (vừa cụ thể vừa ký hiệu) lên từng opcode handler để suy ra khuôn mẫu thanh ghi và toán hạng.	Giải mã ý nghĩa của từng opcode (ADD, XOR, LOAD, STORE, JMP).
wre-vm (CFG & Lifter)	wre vm cfg
wre vm lift	Khôi phục đồ thị luồng điều khiển (CFG) và nâng cấp (lift) trực tiếp luồng bytecode nhị phân ngược trở lại thành code Javascript chuẩn.	Đưa các đoạn mã chạy trong VM ảo hóa về code JS thông thường.
GIAI ĐOẠN 4: Phân Tích Mật Mã Học & Codec Dữ Liệu Dây (Crypto & Wire)
Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-crypto	(Library / Auto)	Cung cấp sẵn các thuật toán đối xứng (XTEA, TEA, AES, RC4), các dòng Checksum (Murmur3, FNV1, FNV1a, CRC32, XorSum) và thuật toán khôi phục chu kỳ lặp khóa (recover.rs).	Tự động nhận diện chữ ký, checksum (như jazoest trong Facebook) và dò tìm khóa XOR lặp lại.
wre-pack	(Library / Auto)	Xử lý các hệ số đếm tùy biến (Custom base-N alphabet), radix đa biến, dò tìm ma trận hoán vị ký tự.	Đọc và sinh các chuỗi mã hóa dạng Base64 biến dị hoặc bảng ký tự alphabet bị xáo trộn.
wre-pow	(Library / Auto)	Động cơ giải Proof-of-Work đa luồng: hỗ trợ chuỗi băm (hash chain), quy tắc tiền tố số 0, folded modulus theo challenge từ máy chủ.	Tự động giải các bài toán PoW của Akamai Pixel, Kasada, Altcha trong vài mili-giây.
wre-wire (Codecs & Schema)	wre wire open
wre wire schema	Giải mã (open) và đóng gói (seal) các payload tầng mạng dạng lồng nhau (gzip + json, base64 + xor + json). Tự động suy diễn schema cấu trúc của payload qua nhiều phiên.	Bóc tách và tái tạo chính xác payload gửi đi của bot sensor.
wre-wire (Diff & Forge)	wre wire diff
wre wire forge	So sánh vi phân theo địa chỉ trường (address path diff) giữa 2 payload. Hỗ trợ lấy payload thật làm donor rồi cấy ghép (forge) các giá trị thay đổi.	Cho phép tái tạo payload hợp lệ bằng kỹ thuật cấy ghép mà không cần tự tính toán toàn bộ 100% các trường.
GIAI ĐOẠN 5: V8 Sandbox & Cơ Chế "Mượn Hàm" Không Cần Viết Lại (V8 Live Mounting)
IMPORTANT

Triết lý cốt lõi của wre-live: "Borrow, do not reimplement" (Hãy mượn, đừng viết lại).
Mã mã hóa của mục tiêu đã được viết sẵn trong file JS của họ và đã đúng 100%. Thay vì tốn hàng tuần dịch ngược thuật toán crypto sang Python, hãy nạp trực tiếp file JS đó vào một V8 Sandbox siêu nhẹ và gọi hàm mã hóa của họ!

Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-live	wre mount	Nhúng trực tiếp V8 engine (C++ bindings). Nạp script mục tiêu, dùng biểu thức chính quy/chữ ký để nhận diện hàm mục tiêu (ví dụ: hàm encrypt, sign, seal) và gọi trực tiếp với tham số tùy ý.	Tái hiện hàm tính toán bảo mật trong 1 dòng lệnh mà không lo bị lệch thuật toán khi vendor cập nhật.
wre-sandbox	wre sandbox	Mô phỏng môi trường trình duyệt ở tầng native V8 C++ bindings (không phải DOM giả lập bằng JS như JSDOM, không dùng Chrome nặng nề). Đi kèm thư viện hồ sơ thiết bị thật (device profiles).	Đánh lừa sensor script tưởng rằng nó đang chạy trong một thiết bị iPhone hoặc Windows thật mà không tốn RAM chạy Chrome.
wre-env	wre env	Bắt trọn đồ thị đối tượng (object graph) của trình duyệt và nạp lười (lazy-materialize) vào V8 realm.	Cung cấp đầy đủ các biến toàn cục mà script yêu cầu mà không bị crash vì undefined.
GIAI ĐOẠN 6: Chống Phát Hiện & Đồng Bộ Đa Phiên Bản (Anti-Detect & Drift)
Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-ident (Locate & Drift)	wre locate
wre drift	Đánh hash hình thái cú pháp hàm (AST Shape Hashing) không phụ thuộc tên biến. Lưu trạng thái vào file targets/<name>.lock. Khi vendor đẩy bản build mới, lệnh wre drift sẽ chỉ ra hàm cũ tương ứng với hàm mới nào.	Duy trì tool chạy ổn định xuyên suốt các lần website cập nhật/đổi tên biến JS hàng ngày.
wre-ident (Build Pairing)	wre builds	So khớp các hàm giữa Version $N$ và Version $N+1$ dựa trên ngưỡng cấu trúc tương đồng (threshold).	Xem nhanh bản cập nhật mới của đối phương đã thêm tính năng chống bot gì mới.
wre-net (Fingerprint Transport)	wre tls	Tùy biến bộ bắt tay TLS (ClientHello, thứ tự cipher suite, extension JA3/JA4) và HTTP/2 fingerprint (SETTINGS frame, header order, window size, HPACK).	Đảm bảo request phát đi từ Python/Rust có vân tay mạng y hệt Google Chrome thật, vượt qua Cloudflare WAF / Akamai Edge.
wre-oracle (Payload Grading)	wre grade	Chấm điểm độ trung thực của payload bạn tự tạo ra so với các payload bắt được từ trình duyệt thật.	Phát hiện sớm các trường bị thiếu hoặc sai định dạng trước khi gửi lên server thật.
wre-variants & wre-markers	wre markers
wre sweep	Kiểm tra 64 dấu vết tự động hóa (automation markers): bao gồm cả dấu vết do công cụ để lại và dấu vết do việc cố tình che giấu để lại (concealment tells).	Đảm bảo môi trường chạy sạch 100%, không bị nhận diện là bot.
GIAI ĐOẠN 7: Đóng Gói Client Headless Tự Động (Codegen & Packaging)
Công cụ / Crate	CLI Lệnh	Cơ chế hoạt động	Bài toán giải quyết
wre-client & wre-clientd	wre client	Kiến trúc Sidecar Daemon (wred): chạy V8 solver ngầm, giao tiếp qua standard IPC pipe (hoặc Unix domain socket) bằng protocol nhị phân bảo mật.	Chạy giải pháp không cần mở browser, tốc độ tính toán tính bằng mili-giây.
wre-codegen	wre client package	Biên dịch từ core Rust ra 4 thư viện SDK hoàn chỉnh: Node.js (NPM), Python (Wheel), Go và Rust.	Cung cấp SDK sẵn dùng cho đồng đội tích hợp vào backend crawler/automation.
