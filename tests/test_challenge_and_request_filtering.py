import pytest
import uuid
import json
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel, NetworkResponseModel, SessionModel
from app.interfaces.mcp.tools.network import list_requests_tool, detect_security_challenges_tool


@pytest.mark.asyncio
async def test_list_requests_with_friendly_name_and_body_keyword():
    session_id = f"sess_test_{uuid.uuid4().hex[:8]}"
    req1_id = f"req_{uuid.uuid4().hex[:8]}"
    req2_id = f"req_{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        # Create dummy session
        sess = SessionModel(
            id=session_id,
            name="Test Filter Session",
            source="test",
            status="COMPLETED",
            started_at_ns=1000,
            created_at_ns=1000,
            updated_at_ns=1000,
        )
        db.add(sess)

        # Req 1: GraphQL with friendly name in headers
        r1 = NetworkRequestModel(
            id=req1_id,
            session_id=session_id,
            method="POST",
            url="https://api.example.com/graphql",
            path="/graphql",
            headers_json=json.dumps({"X-FB-Friendly-Name": "useFXIMUpdateNameMutation"}),
            body_json=json.dumps({"variables": {"name": "Test"}}),
            started_at_ns=1100,
        )
        resp1 = NetworkResponseModel(
            id=f"resp_{uuid.uuid4().hex[:8]}",
            request_id=req1_id,
            status_code=200,
            body_json=json.dumps({"errors": [{"summary": "Secured Action", "description": "{\"challenge_type\": \"reauth\", \"encrypted_context\": \"CTX12345\"}"}]}),
            received_at_ns=1200,
        )

        # Req 2: REST search
        r2 = NetworkRequestModel(
            id=req2_id,
            session_id=session_id,
            method="GET",
            url="https://api.example.com/items?q=shoes",
            path="/items",
            headers_json="{}",
            body_json="{}",
            started_at_ns=1300,
        )
        resp2 = NetworkResponseModel(
            id=f"resp_{uuid.uuid4().hex[:8]}",
            request_id=req2_id,
            status_code=200,
            body_json="[]",
            received_at_ns=1400,
        )

        db.add_all([r1, resp1, r2, resp2])
        await db.commit()

    # 1. Filter by friendly_name
    res_fn = await list_requests_tool(session_id=session_id, friendly_name="useFXIMUpdateNameMutation")
    reqs_fn = res_fn["data"]["requests"]
    assert len(reqs_fn) == 1
    assert reqs_fn[0]["request_id"] == req1_id
    assert reqs_fn[0]["friendly_name"] == "useFXIMUpdateNameMutation"

    # 2. Filter by body_keyword
    res_bk = await list_requests_tool(session_id=session_id, body_keyword="Test")
    reqs_bk = res_bk["data"]["requests"]
    assert len(reqs_bk) == 1
    assert reqs_bk[0]["request_id"] == req1_id

    # 3. Detect security challenge
    res_chal = await detect_security_challenges_tool(session_id=session_id)
    challenges = res_chal["data"]["challenges"]
    assert len(challenges) == 1
    c = challenges[0]
    assert c["trigger_request"]["request_id"] == req1_id
    assert c["challenge_info"]["summary"] == "Secured Action"
    assert c["challenge_info"]["challenge_type"] == "reauth"
    assert c["challenge_info"]["has_encrypted_context"] is True


@pytest.mark.asyncio
async def test_detect_security_challenges_on_real_task():
    """Kiểm tra detect_security_challenges trên session task_b528f651 đã thu thập thực tế."""
    session_id = "sess_task_b528f651_1"
    res = await detect_security_challenges_tool(session_id=session_id)
    if res.get("status") == "COMPLETED" and res["data"]["challenges_found"] > 0:
        challenges = res["data"]["challenges"]
        assert len(challenges) >= 1
        first_c = challenges[0]
        assert first_c["challenge_info"]["challenge_type"] == "reauth"
        assert first_c["is_resolved"] is True
        assert len(first_c["resolution_chain"]) >= 4

