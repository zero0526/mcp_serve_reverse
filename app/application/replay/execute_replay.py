from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkResponseModel
from app.adapters.replay.http_client import HttpxReplayExecutor
from app.application.replay.compare_responses import CompareResponsesUseCase
from app.application.replay.prepare_replay import PrepareReplayUseCase
from app.domain.lineage.entities import ReplaySpec
from app.domain.replay.entities import (
    ReplayComparison,
    ReplayExecutionResult,
    ReplayMode,
    ReplayRequest,
)
from app.domain.replay.policies import ReplaySafetyPolicy
from app.infrastructure.serialization.json import safe_loads
from app.ports.replay import HTTPReplayExecutorPort


class ExecuteReplayUseCase:
    """Use case thực thi Replay Request và so sánh với baseline capture gốc."""

    def __init__(
        self,
        http_executor: HTTPReplayExecutorPort | None = None,
        prepare_use_case: PrepareReplayUseCase | None = None,
        compare_use_case: CompareResponsesUseCase | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.http_executor = http_executor or HttpxReplayExecutor()
        self.prepare_use_case = prepare_use_case or PrepareReplayUseCase()
        self.compare_use_case = compare_use_case or CompareResponsesUseCase()
        self.session_factory = session_factory

    async def execute(
        self,
        spec: ReplaySpec,
        variables: dict[str, Any] | None = None,
        mode: ReplayMode = ReplayMode.DRY_RUN,
        policy: ReplaySafetyPolicy | None = None,
    ) -> tuple[ReplayRequest, ReplayExecutionResult | None, ReplayComparison | None]:
        # 1. Chuẩn bị request với các biến đã giải quyết
        req = self.prepare_use_case.execute(spec, variables)

        # 2. Nếu chế độ DRY_RUN, dừng lại và trả về kết quả chuẩn bị mà không gửi request mạng
        if mode == ReplayMode.DRY_RUN:
            return req, None, None

        # 3. Gửi request thực tế
        exec_result = await self.http_executor.execute(req, policy)

        # 4. Đọc baseline response từ SQLite để so sánh
        expected_status = 200
        expected_body = None
        expected_headers = None

        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(NetworkResponseModel).where(
                NetworkResponseModel.request_id == spec.target_request_id
            )
            resp_row = (await db.execute(stmt)).scalar_one_or_none()

            if not resp_row:
                # Fallback tìm kiếm theo chuỗi ID tương đối
                stmt2 = select(NetworkResponseModel).where(
                    NetworkResponseModel.request_id.like(f"%{spec.target_request_id}%")
                )
                resp_row = (await db.execute(stmt2)).scalar_one_or_none()

            if resp_row:
                expected_status = resp_row.status_code if resp_row.status_code is not None else 200
                expected_body = safe_loads(resp_row.body_json) if resp_row.body_json else None
                expected_headers = safe_loads(resp_row.headers_json) if resp_row.headers_json else {}

        # 5. So sánh kết quả thực thi so với baseline
        comparison = self.compare_use_case.execute(
            target_request_id=spec.target_request_id,
            expected_status=expected_status,
            expected_body=expected_body,
            expected_headers=expected_headers,
            actual_result=exec_result,
        )

        return req, exec_result, comparison
