import sys
import io
import time
import json
from datetime import datetime
from pathlib import Path
import pychrome

from dev.schema import NodeType, RelationType, StateKind
from dev.storage import ValueStore
from dev.graph import CausalGraphBuilder

# Đảm bảo in UTF-8 không lỗi trên Windows PowerShell và xả buffer ngay lập tức (flush)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

def log_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)

def format_stack(initiator):
    """Trích xuất chuỗi V8 Call Stack của JavaScript kích hoạt request."""
    init_type = initiator.get("type", "other")
    stack = initiator.get("stack")
    if not stack or "callFrames" not in stack:
        return init_type, []
    
    frames = []
    for f in stack.get("callFrames", [])[:4]:
        fn = f.get("functionName") or "(anonymous)"
        raw_url = f.get("url", "").split("/")[-1].split("?")[0]
        url = raw_url if raw_url else "inline"
        line = f.get("lineNumber", 0)
        col = f.get("columnNumber", 0)
        frames.append(f"{fn}@{url}:{line}:{col}")
    return init_type, frames

def main():
    log_print("=" * 75)
    log_print(" 🕵️  CDP PASSIVE RECORDER - LẮNG NGHE CHUỖI REQUEST DO NGƯỜI DÙNG THAO TÁC")
    log_print("=" * 75)
    log_print("[*] Đang kết nối tới Chrome (remote debugging port 9222)...")

    try:
        browser = pychrome.Browser(url="http://127.0.0.1:9222")
        tabs = browser.list_tab()
    except Exception as e:
        log_print(f"[!] Không thể kết nối tới Chrome: {e}")
        log_print("    Vui lòng đảm bảo Chrome/CloakBrowser đã chạy với cờ: --remote-debugging-port=9222")
        return

    # Lọc các tab loại 'page'
    page_tabs = [t for t in tabs if t._kwargs.get("type", "page") == "page"]
    if not page_tabs:
        log_print("[!] Không tìm thấy tab trình duyệt nào đang mở!")
        return

    log_print(f"\n[*] Tìm thấy {len(page_tabs)} tab đang mở trong Chrome:")
    for idx, t in enumerate(page_tabs):
        t_title = t._kwargs.get("title", "No Title")
        t_url = t._kwargs.get("url", "")
        log_print(f"  [{idx + 1}] {t_title[:45]} | URL: {t_url[:60]}")

    # Tự động chọn tab không phải about:blank
    selected_idx = 0
    for i, t in enumerate(page_tabs):
        u = t._kwargs.get("url", "")
        if u and "about:blank" not in u and not u.startswith("chrome://"):
            selected_idx = i
            break

    tab = page_tabs[selected_idx]
    active_title = tab._kwargs.get("title", "No Title")
    active_url = tab._kwargs.get("url", "")
    log_print(f"\n[+] Đang bám theo (Attach) Tab [{selected_idx + 1}]: {active_title}")
    log_print(f"    URL hiện tại: {active_url}")
    log_print("\n👉 BÂY GIỜ BẠN HÃY THAO TÁC TRÊN TRÌNH DUYỆT (Click, chuyển trang, điền form, nộp bài...)")
    log_print("👉 Script sẽ chạy ngầm ghi nhận toàn bộ chuỗi request theo thời gian thực.")
    log_print("👉 Nhấn Ctrl + C bất cứ lúc nào để DỪNG và XUẤT BÁO CÁO PHÂN TÍCH CHUỖI REQUEST.\n")
    log_print("-" * 75)

    # Bộ nhớ lưu trữ chuỗi tương tác theo thứ tự thời gian
    session_sequence = []
    captured_requests = {}
    captured_responses = {}
    pending_bodies = {}

    def on_request_will_be_sent(**kwargs):
        req = kwargs.get("request", {})
        req_id = kwargs.get("requestId")
        initiator = kwargs.get("initiator", {})
        timestamp = kwargs.get("wallTime", time.time())
        method = req.get("method", "GET")
        url = req.get("url", "")
        post_data = req.get("postData")
        headers = req.get("headers", {})

        init_type, call_frames = format_stack(initiator)

        record = {
            "index": len(session_sequence) + 1,
            "request_id": req_id,
            "timestamp": timestamp,
            "time_str": datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3],
            "method": method,
            "url": url,
            "headers": headers,
            "post_data": post_data,
            "initiator_type": init_type,
            "call_stack": call_frames,
            "status": None,
            "response_headers": {},
            "response_body": None,
        }

        captured_requests[req_id] = record
        session_sequence.append(record)

        # In log trực quan thời gian thực
        stack_str = f" ➔ JS: {' -> '.join(call_frames[:2])}" if call_frames else ""
        data_preview = f" | Body: {post_data[:60]}..." if post_data else ""
        log_print(f"[{record['time_str']}] #{record['index']:02d} {method:<6} {url[:80]}{data_preview}{stack_str}")

    def on_response_received(**kwargs):
        res = kwargs.get("response", {})
        req_id = kwargs.get("requestId")
        status = res.get("status")
        mime = res.get("mimeType", "")
        resp_headers = res.get("headers", {})

        if req_id in captured_requests:
            captured_requests[req_id]["status"] = status
            captured_requests[req_id]["response_headers"] = resp_headers
            captured_requests[req_id]["mime_type"] = mime

        captured_responses[req_id] = {
            "status": status,
            "mime_type": mime,
            "headers": resp_headers,
        }

    def on_loading_finished(**kwargs):
        req_id = kwargs.get("requestId")
        # Đánh dấu cần lấy body nếu là XHR/Fetch/Document (bỏ qua media, fonts)
        if req_id in captured_requests:
            mime = captured_requests[req_id].get("mime_type", "")
            if any(t in mime for t in ["json", "text", "html", "javascript", "xml"]) or not mime:
                pending_bodies[req_id] = True

    # Bắt sự kiện người dùng điều hướng sang trang mới
    def on_navigated(**kwargs):
        frame = kwargs.get("frame", {})
        if not frame.get("parentId"):  # Main frame
            new_url = frame.get("url")
            log_print(f"\n🌐 [PAGE NAVIGATED] Người dùng chuyển tới: {new_url}\n" + "-" * 60)

    # Đăng ký listeners
    tab.Network.requestWillBeSent = on_request_will_be_sent
    tab.Network.responseReceived = on_response_received
    tab.Network.loadingFinished = on_loading_finished
    tab.Page.frameNavigated = on_navigated

    tab.start()
    tab.Network.enable()
    tab.Page.enable()
    tab.Runtime.enable()

    try:
        while True:
            # Lấy nội dung response body cho các request vừa tải xong
            for r_id in list(pending_bodies.keys()):
                try:
                    body_res = tab.Network.getResponseBody(requestId=r_id)
                    body_text = body_res.get("body")
                    if body_text and r_id in captured_requests:
                        captured_requests[r_id]["response_body"] = body_text
                except Exception:
                    pass
                pending_bodies.pop(r_id, None)

            time.sleep(0.2)

    except KeyboardInterrupt:
        log_print("\n\n" + "=" * 75)
        log_print("🛑 ĐÃ NHẬN LỆNH DỪNG LẮNG NGHE. TIẾN HÀNH XUẤT DỮ LIỆU PHÂN TÍCH...")
        log_print("=" * 75)

    # Lưu chuỗi request ra file JSON để phân tích Lineage & Workflow
    out_dir = Path("dev/captured_sessions")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"session_flow_{int(time.time())}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(session_sequence, f, ensure_ascii=False, indent=2)

    log_print(f"\n[✔] Đã lưu trọn vẹn chuỗi {len(session_sequence)} requests vào:")
    log_print(f"    👉 {out_file.resolve()}")

    # Thống kê nhanh chuỗi thao tác
    post_reqs = [r for r in session_sequence if r["method"] == "POST"]
    js_reqs = [r for r in session_sequence if r["call_stack"]]
    log_print(f"\n📊 BÁO CÁO NHANH CHUỖI THAO TÁC CỦA NGƯỜI DÙNG:")
    log_print(f"  • Tổng số request bắt được : {len(session_sequence)}")
    log_print(f"  • Số request POST (Gửi dữ liệu): {len(post_reqs)}")
    log_print(f"  • Số request kích hoạt bởi JS: {len(js_reqs)}")

    if post_reqs:
        log_print("\n🔎 CÁC REQUEST POST TRỌNG TÂM CẦN PHÂN TÍCH:")
        for pr in post_reqs:
            log_print(f"  - #{pr['index']} POST {pr['url']}")
            if pr.get("post_data"):
                log_print(f"    Payload: {pr['post_data'][:120]}...")
            if pr.get("call_stack"):
                log_print(f"    Call Stack: {' -> '.join(pr['call_stack'])}")

    # Xây dựng CausalGraph theo mô hình Request-Centric & Value-Flow
    builder = CausalGraphBuilder(session_id=f"sess_{int(time.time())}")
    known_cookies = set()

    for rec in session_sequence:
        req_headers = rec.get("headers", {})
        # 1. Trích xuất Cookie từ Request Header lưu vào StateNode
        cookie_header = req_headers.get("cookie") or req_headers.get("Cookie") or ""
        if cookie_header:
            for item in cookie_header.split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    if k and k not in known_cookies:
                        builder.add_cookie_state(
                            name=k,
                            value=v,
                            url=rec["url"],
                            timestamp=rec["timestamp"],
                        )
                        known_cookies.add(k)

        # 2. Thêm RequestNode (Root của trace)
        req_node = builder.add_request(
            request_id=rec["request_id"] or f"req_{rec['index']}",
            url=rec["url"],
            method=rec["method"],
            headers=req_headers,
            body_raw=rec.get("post_data"),
            initiator_type=rec.get("initiator_type", "other"),
            initiator_stack=rec.get("call_stack"),
            timestamp=rec["timestamp"],
        )

        # 3. Phân rã Payload/Cookies thành ValueNodes và tự động truy ngược (Backward Correlation)
        if rec.get("post_data") or cookie_header:
            builder.build_request_lineage(
                request_node=req_node,
                post_data=rec.get("post_data"),
            )

        # 4. Thêm ResponseNode nếu có
        if rec.get("status"):
            builder.add_response(
                request_node=req_node,
                status=rec["status"],
                mime_type=rec.get("mime_type") or "unknown",
                headers=rec.get("response_headers"),
                body_raw=rec.get("response_body"),
                timestamp=rec["timestamp"] + 0.05,
            )

    # Lưu file Causal Graph JSON
    graph_file = out_dir / f"session_graph_{int(time.time())}.json"
    with open(graph_file, "w", encoding="utf-8") as f:
        f.write(builder.graph.model_dump_json(indent=2))

    log_print(f"[✔] Đã xuất Đồ thị Nhân quả Chuẩn hóa (Request-Centric Causal Graph):")
    log_print(f"    👉 {graph_file.resolve()}")
    log_print(f"    • Tổng số Nodes: {len(builder.graph.nodes)}")
    req_count = sum(1 for n in builder.graph.nodes.values() if n.node_type == NodeType.REQUEST)
    val_count = sum(1 for n in builder.graph.nodes.values() if n.node_type == NodeType.VALUE)
    fn_count = sum(1 for n in builder.graph.nodes.values() if n.node_type == NodeType.FUNCTION)
    log_print(f"      (Requests: {req_count}, Values: {val_count}, JS Functions: {fn_count})")
    log_print(f"    • Tổng số Cạnh Nhân quả (Edges): {len(builder.graph.edges)}")

    # Dừng an toàn không ngắt kết nối browser của người dùng
    try:
        tab.stop()
    except Exception:
        pass
    log_print("\n[*] Đã ngắt kết nối an toàn (Trình duyệt của bạn vẫn hoạt động bình thường).")

if __name__ == "__main__":
    main()