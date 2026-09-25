"""
Kiểm thử toàn diện Mô hình Đồ thị Nhân quả Lấy Request làm Trung tâm (Request-Centric & Value-Flow).
Kịch bản Reverse Engineering thực tế:
1. Khởi tạo Trạng thái môi trường (StateNodes):
   - DOM input: email, password
   - DOM SSR: csrf_token
   - LocalStorage: device_fp
   - Cookie: SESSION_ID
2. Request 1: POST /api/v1/auth/login
   - V8 Initiator Call Stack: loginHandler -> buildPayload -> fetch
   - Headers: Cookie
   - Body: JSON { email, password, csrf_token, device_fp }
3. Backward Trace (Truy ngược):
   - Phân rã Request thành từng ValueNode
   - Khẳng định 100% từng field trong Request đều tìm về đúng State gốc (DOM, Storage, Cookie)
4. Response 1: 200 OK trả về { "access_token": "jwt_token_alpha_omega_999" }
5. Forward Trace (Truy xuôi):
   - Xử lý Response qua hàm handleLoginSuccess
   - Ghi token vào LocalStorage["jwt"]
   - Kích hoạt Request 2: GET /api/v1/user/me với Header "Authorization: Bearer jwt_..."
   - Kiểm tra chuỗi tác động xuôi dòng từ Response 1 sang Request 2
"""

import io
import json
import sys
import time
from pathlib import Path

# Đảm bảo in UTF-8 không lỗi trên Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from dev.schema import (
    CausalGraph,
    NodeType,
    RelationType,
    RequestNode,
    ResponseNode,
    StateKind,
    StateNode,
    ValueNode,
)
from dev.storage import ValueStore
from dev.graph import CausalGraphBuilder


def test_request_centric_workflow(tmp_dir: Path):
    print("\n" + "=" * 80)
    print("🚀 BẮT ĐẦU TEST: REQUEST-CENTRIC & VALUE-FLOW CAUSAL GRAPH (REVERSE ENGINEERING)")
    print("=" * 80)

    store = ValueStore(storage_dir=tmp_dir / "blobs")
    builder = CausalGraphBuilder(session_id="re_session_demo", value_store=store)
    t0 = time.time()

    # -------------------------------------------------------------------------
    # BƯỚC 1: KHỞI TẠO TRẠNG THÁI MÔI TRƯỜNG (DOM, COOKIE, STORAGE)
    # -------------------------------------------------------------------------
    print("\n[*] 1. Khởi tạo StateNodes trong trình duyệt...")
    dom_csrf = builder.add_dom_state(
        key="script#__NEXT_DATA__",
        value="sec_csrf_token_ssr_987654",
        tag="script",
        input_type="ssr_json",
        url="https://app.example.com/login",
        timestamp=t0,
    )
    dom_email = builder.add_dom_state(
        key="input#email",
        value="reverse_engineer@google.com",
        tag="input",
        input_type="text",
        url="https://app.example.com/login",
        timestamp=t0 + 0.1,
    )
    dom_pass = builder.add_dom_state(
        key="input#password",
        value="super_secret_p@ssword",
        tag="input",
        input_type="password",
        url="https://app.example.com/login",
        timestamp=t0 + 0.2,
    )
    storage_fp = builder.add_storage_state(
        key="device_fp",
        value="hw_fingerprint_hash_112233",
        kind="localStorage",
        timestamp=t0 + 0.3,
    )
    cookie_sess = builder.add_cookie_state(
        name="SESSION_ID",
        value="sess_cookie_guid_778899",
        domain="app.example.com",
        timestamp=t0 + 0.4,
    )
    print("    [✔] Đã tạo 5 StateNodes: DOM CSRF (SSR), DOM Email, DOM Password, Storage FP, Cookie SESSION_ID")

    # -------------------------------------------------------------------------
    # BƯỚC 2: PHÁT SINH REQUEST LOGIN (ROOT TRACE 1)
    # -------------------------------------------------------------------------
    print("\n[*] 2. Ghi nhận Request Login (POST /api/v1/auth/login)...")
    req_login = builder.add_request(
        request_id="req_cdp_101",
        url="https://app.example.com/api/v1/auth/login",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Cookie": "SESSION_ID=sess_cookie_guid_778899; theme=dark",
        },
        body_raw={
            "email": "reverse_engineer@google.com",
            "password": "super_secret_p@ssword",
            "csrf_token": "sec_csrf_token_ssr_987654",
            "device_fp": "hw_fingerprint_hash_112233",
        },
        initiator_type="script",
        initiator_stack=[
            "buildPayload@auth.js:35:10",
            "loginHandler@auth.js:12:4",
        ],
        timestamp=t0 + 1.0,
    )
    print(f"    [✔] Tạo RequestNode Root: id={req_login.id}, url={req_login.url}")

    # Phân rã Payload & tự động truy ngược (Backward Correlation)
    created_values = builder.build_request_lineage(
        request_node=req_login,
        post_data=store.load(req_login.body.ref),
    )
    print(f"    [✔] Phân rã thành {len(created_values)} ValueNodes con:")
    for v in created_values:
        print(f"        • ValueNode: id={v.id}, name='{v.name}', val='{v.value.preview}'")

    # -------------------------------------------------------------------------
    # BƯỚC 3: KIỂM TRA BACKWARD TRACE (TRUY NGƯỢC NGUỒN GỐC)
    # -------------------------------------------------------------------------
    print("\n[*] 3. Kiểm tra BACKWARD TRACE: Mỗi trường của Request được tạo từ đâu?")
    trace_back_result = builder.graph.trace_backward(req_login.id)
    field_origins = trace_back_result["field_origins"]
    assert len(field_origins) >= 5, f"Cần ít nhất 5 nhánh (4 body fields + 1 cookie), có {len(field_origins)}"

    matched_origins = {}
    for item in field_origins:
        val_node: ValueNode = item["node"]
        edge = item["edge"]
        origins = item["origins"]
        if origins:
            origin_state = origins[0]["node"]
            matched_origins[val_node.name] = (origin_state.kind, origin_state.key)
            print(f"    🔍 Field '{val_node.name}' (id={val_node.id}) ◄──[{origins[0]['edge'].relation}]── {origin_state.kind.value}[{origin_state.key}] (Conf: {origins[0]['edge'].confidence})")

    assert "email" in matched_origins and matched_origins["email"][0] == StateKind.DOM
    assert "password" in matched_origins and matched_origins["password"][0] == StateKind.DOM
    assert "csrf_token" in matched_origins and matched_origins["csrf_token"][0] == StateKind.DOM
    assert "device_fp" in matched_origins and matched_origins["device_fp"][0] == StateKind.STORAGE
    assert "Cookie:SESSION_ID" in matched_origins and matched_origins["Cookie:SESSION_ID"][0] == StateKind.COOKIE
    print("\n    🎉 [PASSED] BACKWARD TRACE HOÀN TOÀN CHÍNH XÁC 100% CẢ 5 TRƯỜNG DỮ LIỆU!")

    # -------------------------------------------------------------------------
    # BƯỚC 4: RESPONSE TRẢ VỀ & FORWARD TRACE (TRUY XUÔI TÁC ĐỘNG)
    # -------------------------------------------------------------------------
    print("\n[*] 4. Ghi nhận Response 200 OK & Tiêu thụ Token (Forward Trace)...")
    res_login = builder.add_response(
        request_node=req_login,
        status=200,
        mime_type="application/json",
        body_raw={
            "status": "success",
            "token": "jwt_token_alpha_omega_999",
            "expires_in": 3600,
        },
        timestamp=t0 + 1.2,
    )
    print(f"    [✔] Tạo ResponseNode: id={res_login.id}, status=200, liên kết RESPONDS_TO với {req_login.id}")

    # Giả lập Client nhận Response, trích xuất token và ghi vào localStorage
    jwt_storage_state = builder.add_storage_state(
        key="jwt_token",
        value="jwt_token_alpha_omega_999",
        kind="localStorage",
        timestamp=t0 + 1.25,
    )

    builder.correlate_response_consumption(
        response_node=res_login,
        consumer_fn_name="handleLoginSuccess",
        target_state_node=jwt_storage_state,
        extracted_token_key="access_token",
    )

    # Giả lập Request 2: GET /api/v1/user/me sử dụng Token vừa lưu
    print("\n[*] 5. Ghi nhận Request 2 (GET /api/v1/user/me) sử dụng Token từ Response 1...")
    req_profile = builder.add_request(
        request_id="req_cdp_102",
        url="https://app.example.com/api/v1/user/me",
        method="GET",
        headers={
            "Authorization": "Bearer jwt_token_alpha_omega_999",
        },
        timestamp=t0 + 1.5,
    )

    # Thiết lập liên kết: State (jwt_token) -> Request 2
    builder.graph.add_edge(
        from_id=jwt_storage_state.id,
        to_id=req_profile.id,
        relation=RelationType.READS,
        confidence=0.99,
        evidence=["auth_bearer_exact_match"],
    )

    # Kiểm tra Forward Trace từ Response 1
    print("\n[*] 6. Kiểm tra FORWARD TRACE: Response 1 ảnh hưởng tới đâu?")
    trace_forward_result = builder.graph.trace_forward(res_login.id)
    impacts = trace_forward_result["impacts"]
    assert len(impacts) >= 1, "Phải tìm thấy consumer cho Response 1"

    consumer_fn = impacts[0]["node"]
    downstream_from_fn = impacts[0]["downstream"]
    val_jwt = downstream_from_fn[0]["node"]
    state_jwt = downstream_from_fn[0]["descendants"][0]["node"]
    final_req = downstream_from_fn[0]["descendants"][0]["descendants"][0]["node"]

    print(f"    📈 Chuỗi tác động xuôi dòng:")
    print(f"       Response ({res_login.id})")
    print(f"         └── [CONSUMES] ──> {consumer_fn.node_type.value}: {consumer_fn.name}")
    print(f"               └── [PRODUCES] ──> {val_jwt.node_type.value}: {val_jwt.name}")
    print(f"                     └── [WRITES] ──> {state_jwt.kind.value}[{state_jwt.key}]")
    print(f"                           └── [READS] ──> {final_req.node_type.value}: {final_req.method} {final_req.url}")

    assert final_req.id == req_profile.id, "Forward trace phải chỉ tới Request Profile!"
    print("\n    🎉 [PASSED] FORWARD TRACE CHUỖI RESPONSE -> TOKEN -> REQUEST TIẾP THEO THÀNH CÔNG 100%!")

    # -------------------------------------------------------------------------
    # BƯỚC 7: SERIALIZATION KIỂM TRA ĐỘ GỌN NHẸ
    # -------------------------------------------------------------------------
    print("\n[*] 7. Kiểm tra Serialization Pydantic v2 JSON...")
    json_str = builder.graph.model_dump_json(indent=2)
    reloaded = CausalGraph.model_validate_json(json_str)
    assert len(reloaded.nodes) == len(builder.graph.nodes)
    assert len(reloaded.edges) == len(builder.graph.edges)
    print(f"    [✔] Đồ thị hoàn chỉnh: {len(reloaded.nodes)} Nodes, {len(reloaded.edges)} Edges.")
    print(f"    [✔] Kích thước JSON: {len(json_str.encode('utf-8'))} bytes.")

    print("\n" + "=" * 80)
    print("🏆 TẤT CẢ TEST ĐỀU THÀNH CÔNG RỰC RỠ! MÔ HÌNH HOÀN TOÀN ĐÚNG TRỌNG TÂM REVERSE.")
    print("=" * 80)


def main():
    test_dir = Path("dev/test_tmp_req_centric")
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        test_request_centric_workflow(test_dir)
    finally:
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
