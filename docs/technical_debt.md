**Detect 2fa requets**: 
Tool mới: detect_security_challenges (Phát hiện thử thách bảo mật)
Chức năng:
Tự động quét session: Quét các request bị chặn bởi lỗi HTTP (400, 401, 403, 429) hoặc lỗi nghiệp vụ bảo mật (Secured Action, challenge_type, 2fa, reauth, captcha, checkpoint).
Trích xuất thông tin thử thách:
Loại thử thách: reauth, 2fa_otp, captcha...
Tóm tắt lỗi: summary, error_code.
Ngữ cảnh mã hóa: encrypted_context (dùng để map với các bước gửi OTP).
Lần vết chuỗi giải quyết (resolution_chain):
Tự động xâu chuỗi tất cả các request tiếp theo liên quan đến thử thách này theo thứ tự thời gian.
Gán nhãn mục đích cho từng bước: QUERY_2FA_METHODS, DISPATCH_OTP_CODE, VALIDATE_CHALLENGE_CODE, ACTION_RETRY.
Đánh giá xem thử thách đã được giải quyết thành công hay chưa (is_resolved: true).
Mã nguồn:


[app/interfaces/mcp/tools/network.py]


[app/interfaces/mcp/server.py]

**Test**
Điểm nghẽn 3: Body dạng form-urlencoded chứa chuỗi JSON lồng nhau chưa được tự động parse [ĐÃ XỬ LÝ - RESOLVED]
- Vấn đề: Body của Facebook GraphQL có dạng `variables=%7B%22identity_ids%22...%7D`. Tool trả về chuỗi URL-encoded thô rất dài, làm tiêu tốn rất nhiều Context Token của Agent và dễ gây lỗi parsing. Đồng thời response chứa tiền tố CSRF (`for (;;);`) hoặc chuỗi JSON lồng trong trường lỗi (`errors[0].description`).
- Giải pháp đã triển khai:
  1. Xây dựng engine `parse_smart_payload` trong [json.py](file:///data/projects/web-apps/cli/mcp_server_reverse/app/infrastructure/serialization/json.py):
     - Tự động bóc tách anti-CSRF prefixes (`for (;;);`, `while(1);`, `)]}',\n`, `/*-secure-*/`).
     - Tự động phân rã chuỗi `application/x-www-form-urlencoded`, phát hiện các tham số chứa JSON lồng (như `variables`), giải mã URL và đệ quy parse thành Dict/List cấu trúc.
     - Tự động bóc các chuỗi JSON lồng sâu trong Dict (như `errors[0]["description"]`).
     - Tự động nhận diện streaming/NDJSON (Facebook BigPipe/Comet streaming lines).
  2. Tích hợp sâu vào:
     - [SummarizeRequestUseCase](file:///data/projects/web-apps/cli/mcp_server_reverse/app/application/network/summarize_request.py): Tự động bóc tách và phân cấp request/response body trước khi đưa qua `redact_sensitive_payload`.
     - [Request MCP Resource](file:///data/projects/web-apps/cli/mcp_server_reverse/app/interfaces/mcp/resources/request_resource.py): `request://{session_id}/{request_id}` trả về cấu trúc JSON phân cấp chuẩn cho LLM Agent.
     - [GraphProjector](file:///data/projects/web-apps/cli/mcp_server_reverse/app/adapters/graph/graph_projector.py): `_flatten_leaves` trích xuất đến từng biến con trong `variables` (như `body.variables.full_name`, `body.variables.identity_ids`) phục vụ Data Lineage đồ thị.
---