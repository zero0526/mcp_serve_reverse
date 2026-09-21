from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.graph.graph_projector import _flatten_leaves
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel, SessionModel
from app.domain.lineage.differential import FieldVariance, SessionComparisonResult
from app.domain.lineage.entities import ParameterType
from app.infrastructure.serialization.json import safe_loads
from app.ports.repositories import SessionRepositoryPort


class DifferentialAnalysisUseCase:
    """Use case so sánh vi phân đa phiên thuộc cùng Task ID để phân loại tham số."""

    def __init__(
        self,
        session_repository: SessionRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.session_repo = session_repository
        self.session_factory = session_factory

    async def execute(self, task_id: str) -> SessionComparisonResult:
        async with self.session_factory() as db:  # type: AsyncSession
            # 1. Lấy tất cả session của task_id
            sess_stmt = select(SessionModel).order_by(SessionModel.started_at_ns.asc())
            all_sessions = (await db.execute(sess_stmt)).scalars().all()

            matched_sessions: list[SessionModel] = []
            for s in all_sessions:
                meta = safe_loads(s.metadata_json) if s.metadata_json else {}
                if meta.get("task_id") == task_id or s.id == task_id:
                    matched_sessions.append(s)

            if not matched_sessions:
                return SessionComparisonResult(
                    task_id=task_id,
                    session_ids=[],
                    variances=[],
                    summary={},
                )

            session_ids = [s.id for s in matched_sessions]

            # 2. Lấy toàn bộ Network Requests của các session
            req_stmt = select(NetworkRequestModel).where(
                NetworkRequestModel.session_id.in_(session_ids)
            ).order_by(NetworkRequestModel.started_at_ns.asc())
            requests = (await db.execute(req_stmt)).scalars().all()

        # Nhóm request theo chữ ký (method + path)
        # gom các giá trị của từng field path theo session
        field_values_by_path: dict[str, dict[str, Any]] = {}

        for req in requests:
            sess_id = req.session_id
            headers = safe_loads(req.headers_json) if req.headers_json else {}
            query = safe_loads(req.query_json) if req.query_json else {}
            body = safe_loads(req.body_json) if req.body_json else None

            # Phân rã lá cho Headers
            for k, v in headers.items():
                p = f"headers.{k.lower()}"
                field_values_by_path.setdefault(p, {})[sess_id] = v

            # Phân rã lá cho Query
            for k, v in (query or {}).items():
                p = f"query.{k}"
                field_values_by_path.setdefault(p, {})[sess_id] = v

            # Phân rã lá cho Body
            if body:
                body_leaves = _flatten_leaves(body, prefix="body")
                for p, v in body_leaves:
                    field_values_by_path.setdefault(p, {})[sess_id] = v

        variances: list[FieldVariance] = []
        classified_variables: list[str] = []
        classified_tokens: list[str] = []
        classified_constants: list[str] = []

        # 3. Đánh giá phân loại từng trường
        for path, values_map in field_values_by_path.items():
            distinct_values = set(str(v) for v in values_map.values())
            is_constant = len(distinct_values) <= 1
            sample_val = next(iter(values_map.values())) if values_map else None

            p_lower = path.lower()

            if is_constant:
                param_type = ParameterType.CONSTANT
                inferred_purpose = "Static parameter or fixed header"
                classified_constants.append(path)
            else:
                if "content-length" in p_lower:
                    param_type = ParameterType.CONSTANT
                    inferred_purpose = "Auto-computed transport content length"
                    classified_constants.append(path)
                # Kiểm tra timestamp
                elif isinstance(sample_val, (int, float)) and sample_val > 1_000_000_000_000:
                    param_type = ParameterType.TIMESTAMP
                    inferred_purpose = "Epoch millisecond timestamp"
                # Kiểm tra session token / auth
                elif "auth" in p_lower or "token" in p_lower or "cookie" in p_lower or "session" in p_lower or "redacted" in str(sample_val).lower():
                    param_type = ParameterType.SESSION_TOKEN
                    inferred_purpose = "Session authorization token or cookie"
                    classified_tokens.append(path)
                # Kiểm tra nonce
                elif "nonce" in p_lower or "uuid" in p_lower:
                    param_type = ParameterType.EPHEMERAL_NONCE
                    inferred_purpose = "Per-request nonce"
                # Mặc định coi là input biến thiên của người dùng
                else:
                    param_type = ParameterType.USER_INPUT
                    inferred_purpose = "User-supplied input payload variable"
                    classified_variables.append(path)

            variances.append(
                FieldVariance(
                    path=path,
                    param_type=param_type,
                    values_per_session=values_map,
                    is_constant=is_constant,
                    inferred_purpose=inferred_purpose,
                )
            )

        summary = {
            "total_fields": len(variances),
            "constant_count": len(classified_constants),
            "variable_count": len(classified_variables),
            "token_count": len(classified_tokens),
        }

        return SessionComparisonResult(
            task_id=task_id,
            session_ids=session_ids,
            variances=variances,
            classified_variables=classified_variables,
            classified_tokens=classified_tokens,
            classified_constants=classified_constants,
            summary=summary,
        )
