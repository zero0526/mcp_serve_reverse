import time
import uuid
from pathlib import Path
import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.ingest.ingest_event import IngestEventUseCase
from app.application.replay.resolve_dependencies import ResolveDependenciesUseCase
from app.application.replay.validate_replay import ValidateReplayUseCase
from app.domain.replay.entities import ReplayRequest
from app.domain.replay.policies import ReplaySafetyPolicy
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope


def test_crypto_js_primitives_instrumentation():
    """Kiểm tra tệp crypto.js đã tích hợp đầy đủ các hook nguyên thủy (Primitives, WASM, Worker)."""
    crypto_js_path = Path("app/adapters/browser/instrumentation/crypto.js")
    assert crypto_js_path.exists()
    content = crypto_js_path.read_text(encoding="utf-8")

    # 1. WebCrypto & CSPRNG
    assert "crypto.getRandomValues" in content
    assert "subtle.digest" in content
    assert "subtle.sign" in content

    # 2. Encoding Primitives
    assert "TextEncoder.prototype.encode" in content
    assert "window.btoa" in content
    assert "window.atob" in content

    # 3. WebAssembly
    assert "WebAssembly.instantiate" in content

    # 4. Web Worker
    assert "window.Worker" in content
    assert "worker.postMessage" in content


@pytest.mark.asyncio
async def test_validate_replay_safety_policy():
    """Kiểm thử use case kiểm tra chính sách an toàn Replay (ValidateReplayUseCase)."""
    validator = ValidateReplayUseCase()

    policy = ReplaySafetyPolicy(
        allowed_hosts=["api.example.com"],
        allowed_methods=["GET", "POST"],
        allow_mutation=True,
    )

    # 1. Request hợp lệ
    safe_req = ReplayRequest(
        method="POST",
        url="https://api.example.com/data",
        headers={"content-type": "application/json", "authorization": "Bearer valid_token_123"},
        body={"query": "test"},
    )
    res_safe = validator.execute(safe_req, policy)
    assert res_safe["is_valid"] is True
    assert res_safe["risk_level"] == "LOW"
    assert len(res_safe["violations"]) == 0

    # 2. Vi phạm Whitelist Domain
    unauthorized_host_req = ReplayRequest(
        method="POST",
        url="https://evil-hacker.com/steal",
        headers={"content-type": "application/json"},
    )
    res_host = validator.execute(unauthorized_host_req, policy)
    assert res_host["is_valid"] is False
    assert res_host["risk_level"] == "BLOCKED"
    assert any("not in allowed hosts" in v for v in res_host["violations"])

    # 3. Vi phạm Unreplaced Placeholders
    placeholder_req = ReplayRequest(
        method="POST",
        url="https://api.example.com/checkout",
        headers={"authorization": "Bearer {{auth_token}}"},
        body={"amount": 100, "nonce": "{{nonce}}"},
    )
    res_placeholder = validator.execute(placeholder_req, policy)
    assert res_placeholder["is_valid"] is False
    assert res_placeholder["risk_level"] == "BLOCKED"
    assert any("unreplaced template placeholders" in v for v in res_placeholder["violations"])

    # 4. Vi phạm Redacted Token chưa được thay thế
    redacted_req = ReplayRequest(
        method="POST",
        url="https://api.example.com/orders",
        headers={"authorization": "Bearer [REDACTED:sha256:abc12345]"},
    )
    res_redacted = validator.execute(redacted_req, policy)
    assert res_redacted["is_valid"] is False
    assert any("contains redacted placeholder" in v for v in res_redacted["violations"])

    # 5. Vi phạm State-mutating method khi allow_mutation=False
    read_only_policy = ReplaySafetyPolicy(
        allowed_hosts=["api.example.com"],
        allow_mutation=False,
    )
    mutate_req = ReplayRequest(
        method="DELETE",
        url="https://api.example.com/item/1",
    )
    res_mutate = validator.execute(mutate_req, read_only_policy)
    assert res_mutate["is_valid"] is False
    assert any("State-mutating method" in v for v in res_mutate["violations"])


@pytest.mark.asyncio
async def test_resolve_dependencies_login_to_action():
    """Kiểm thử tự động phát hiện và giải quyết chuỗi phụ thuộc tuần tự (ResolveDependenciesUseCase)."""
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)
    resolve_uc = ResolveDependenciesUseCase(session_factory=AsyncSessionLocal)

    session_id = f"sess_dep_{uuid.uuid4().hex[:8]}"
    await session_repo.create(session_id=session_id, name="Dep Test", target="https://example.com")

    t_base = time.time_ns()

    login_req_id = f"req_login_{uuid.uuid4().hex[:8]}"
    action_req_id = f"req_action_{uuid.uuid4().hex[:8]}"
    token_val = "jwt_live_secure_token_xyz987"

    # 1. Ingest Login Request & Response
    evt_login_req = EventEnvelope(
        event_id=f"evt_lreq_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=t_base + 10_000_000,
        payload={
            "request_id": login_req_id,
            "method": "POST",
            "url": "https://api.example.com/auth/login",
            "headers": {"content-type": "application/json"},
            "body": '{"username": "admin", "password": "secret"}',
        },
    )
    evt_login_res = EventEnvelope(
        event_id=f"evt_lres_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_RESPONSE,
        timestamp_ns=t_base + 20_000_000,
        payload={
            "request_id": login_req_id,
            "status_code": 200,
            "headers": {"set-cookie": "session_id=sess_cookie_123; Path=/; HttpOnly"},
            "body": {"status": "ok", "token": token_val, "user_id": 42},
        },
    )

    # 2. Ingest Action Request (Phụ thuộc vào token và cookie từ login)
    evt_action_req = EventEnvelope(
        event_id=f"evt_areq_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        event_type=EventType.NETWORK_REQUEST,
        timestamp_ns=t_base + 30_000_000,
        payload={
            "request_id": action_req_id,
            "method": "POST",
            "url": "https://api.example.com/account/update",
            "headers": {
                "content-type": "application/json",
                "authorization": f"Bearer {token_val}",
                "cookie": "session_id=sess_cookie_123",
            },
            "body": '{"bio": "Reverse Engineer"}',
        },
    )

    await ingest_uc.execute(evt_login_req)
    await ingest_uc.execute(evt_login_res)
    await ingest_uc.execute(evt_action_req)

    # 3. Chạy ResolveDependenciesUseCase cho action_req_id
    plan = await resolve_uc.execute(session_id=session_id, target_request_id=action_req_id)

    assert plan["has_dependencies"] is True
    assert plan["dependency_count"] == 1

    pre = plan["prerequisites"][0]
    assert pre["request_id"] == login_req_id
    assert pre["method"] == "POST"
    assert "/auth/login" in pre["url"]

    # Kiểm tra extraction rules
    rules = pre["extract_rules"]
    assert len(rules) >= 1
    # Có ít nhất 1 rule ánh xạ token hoặc cookie
    assert any("token" in r["target_variable"] for r in rules) or any("cookie" in r["target_variable"] for r in rules)

    # Kiểm tra Execution Plan
    assert len(plan["execution_plan"]) == 2
    assert "POST https://api.example.com/auth/login" in plan["execution_plan"][0]
    assert "POST https://api.example.com/account/update" in plan["execution_plan"][1]
