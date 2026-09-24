import pytest
import uuid
import json
from app.infrastructure.serialization.json import parse_smart_payload
from app.application.network.summarize_request import SummarizeRequestUseCase
from app.interfaces.mcp.resources.request_resource import get_request_resource
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel, NetworkResponseModel, SessionModel


def test_parse_form_urlencoded_with_nested_json():
    raw = (
        "av=61586402792082&__user=61586402792082&fb_dtsg=NAcTEST&jazoest=25432"
        "&variables=%7B%22client_mutation_id%22%3A%2255ade0fc%22%2C%22identity_ids%22%3A%5B%2261586402792082%22%5D%2C%22full_name%22%3A%22D%C5%A9ng%20Nguy%E1%BB%85n%22%7D"
        "&doc_id=1048361770"
    )
    parsed = parse_smart_payload(raw)
    assert isinstance(parsed, dict)
    assert parsed["av"] == "61586402792082"
    assert parsed["doc_id"] == "1048361770"
    assert parsed["fb_dtsg"] == "NAcTEST"
    assert isinstance(parsed["variables"], dict)
    assert parsed["variables"]["client_mutation_id"] == "55ade0fc"
    assert parsed["variables"]["identity_ids"] == ["61586402792082"]
    assert parsed["variables"]["full_name"] == "Dũng Nguyễn"


def test_parse_anti_csrf_prefix_and_nested_json_error():
    raw_response = (
        'for (;;);{"data": null, "errors": ['
        '{"summary": "Secured Action", "code": 2136001, '
        '"description": "{\\"challenge_type\\": \\"reauth\\", \\"account_id\\": 61586402792082, \\"encrypted_context\\": \\"SEC_CTX_123\\"}"}'
        ']}'
    )
    parsed = parse_smart_payload(raw_response)
    assert isinstance(parsed, dict)
    assert parsed["data"] is None
    assert len(parsed["errors"]) == 1
    err = parsed["errors"][0]
    assert err["summary"] == "Secured Action"
    assert err["code"] == 2136001
    assert isinstance(err["description"], dict)
    assert err["description"]["challenge_type"] == "reauth"
    assert err["description"]["account_id"] == 61586402792082
    assert err["description"]["encrypted_context"] == "SEC_CTX_123"


def test_parse_ndjson_streaming():
    raw = 'for (;;);{"batch": 1, "data": {"user_id": 101}}\nfor (;;);{"batch": 2, "data": {"user_id": 102}}'
    parsed = parse_smart_payload(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["batch"] == 1
    assert parsed[0]["data"]["user_id"] == 101
    assert parsed[1]["batch"] == 2
    assert parsed[1]["data"]["user_id"] == 102


def test_parse_pure_url_encoded_json():
    raw = "%7B%22action%22%3A%22execute%22%2C%22params%22%3A%7B%22step%22%3A1%7D%7D"
    parsed = parse_smart_payload(raw)
    assert isinstance(parsed, dict)
    assert parsed["action"] == "execute"
    assert parsed["params"]["step"] == 1


def test_plain_text_and_code_not_misparsed():
    # Plain text sentences with = should not become corrupted
    t1 = "Hello world, this is a plain text with = sign"
    assert parse_smart_payload(t1) == t1

    # HTML content should remain string
    t2 = "<html><body>Response = Success</body></html>"
    assert parse_smart_payload(t2) == t2

    # Javascript bundle code
    t3 = '/*FB_PKG_DELIM*/\n\n__d("AMLoggingUtils",[],(function(t,n,r,o,a,i){var e = 1;}))'
    assert parse_smart_payload(t3) == t3


@pytest.mark.asyncio
async def test_summarize_request_and_resource_with_smart_payload():
    session_id = f"sess_smart_{uuid.uuid4().hex[:8]}"
    req_id = f"req_{uuid.uuid4().hex[:8]}"

    raw_req_body = (
        "av=61586402792082&fb_dtsg=NAcTOKEN_VAL&password=my_secret_pass"
        "&variables=%7B%22identity_id%22%3A%22123%22%2C%22api_key%22%3A%22KEY_SECRET_999%22%7D"
    )
    raw_res_body = (
        'for (;;);{"data": {"status": "SUCCESS"}, "errors": [{"description": "{\\"challenge_type\\": \\"reauth\\"}"}]}'
    )

    async with AsyncSessionLocal() as db:
        # Create session
        sess = SessionModel(
            id=session_id,
            source="browser",
            name="Smart Parsing Test",
            status="active",
            target="https://facebook.com",
            started_at_ns=1000,
            created_at_ns=1000,
            updated_at_ns=1000,
        )
        db.add(sess)

        # Create request with form-urlencoded body
        req = NetworkRequestModel(
            id=req_id,
            session_id=session_id,
            url="https://accountscenter.facebook.com/api/graphql/",
            method="POST",
            host="accountscenter.facebook.com",
            path="/api/graphql/",
            resource_type="xhr",
            started_at_ns=1000,
            headers_json=json.dumps({"Content-Type": "application/x-www-form-urlencoded"}),
            body_json=json.dumps(raw_req_body),
        )
        db.add(req)

        # Create response with anti-csrf & nested json
        res = NetworkResponseModel(
            id=f"res_{uuid.uuid4().hex[:8]}",
            request_id=req_id,
            status_code=200,
            received_at_ns=2000,
            headers_json=json.dumps({"Content-Type": "application/json"}),
            body_json=json.dumps(raw_res_body),
        )
        db.add(res)
        await db.commit()

    # 1. Test SummarizeRequestUseCase
    uc = SummarizeRequestUseCase(session_factory=AsyncSessionLocal)
    summary = await uc.execute(session_id=session_id, request_id=req_id, redaction_mode="strict")
    assert summary is not None

    req_body = summary["body"]
    assert isinstance(req_body, dict)
    assert req_body["av"] == "61586402792082"
    # Kiểm tra biến variables được parse thành dict
    assert isinstance(req_body["variables"], dict)
    assert req_body["variables"]["identity_id"] == "123"
    # Kiểm tra redaction hoạt động bên trong nested variables và form params
    assert req_body["variables"]["api_key"] == "[REDACTED]"
    assert req_body["password"] == "[REDACTED]"

    # Kiểm tra response body được parse
    res_body = summary["response"]["body"]
    assert isinstance(res_body, dict)
    assert res_body["data"]["status"] == "SUCCESS"
    assert res_body["errors"][0]["description"]["challenge_type"] == "reauth"

    # 2. Test get_request_resource (request://{session_id}/{request_id})
    res_str = await get_request_resource(session_id=session_id, request_id=req_id, redaction_mode="strict")
    resource_payload = json.loads(res_str)
    assert "request" in resource_payload
    res_req_body = resource_payload["request"]["body"]
    assert isinstance(res_req_body, dict)
    assert isinstance(res_req_body["variables"], dict)
    assert res_req_body["variables"]["identity_id"] == "123"
