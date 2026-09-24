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


