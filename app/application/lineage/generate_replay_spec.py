import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.domain.lineage.entities import ParameterType, ReplaySpec, ReplayStepSpec
from app.infrastructure.serialization.json import safe_loads
from app.ports.graph_repository import GraphRepositoryPort


class GenerateReplaySpecUseCase:
    """Use case đóng gói ReplaySpec chuẩn mực bàn giao cho Phase 3 (Replay Engine)."""

    def __init__(
        self,
        graph_repository: GraphRepositoryPort,
        diff_use_case: DifferentialAnalysisUseCase | None = None,
        trace_use_case: TraceLineageUseCase | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.graph_repo = graph_repository
        self.diff_use_case = diff_use_case or DifferentialAnalysisUseCase(session_factory=session_factory)
        self.trace_use_case = trace_use_case or TraceLineageUseCase(graph_repository)
        self.session_factory = session_factory

    async def execute(
        self,
        task_id: str,
        target_request_id: str,
    ) -> ReplaySpec:
        # 1. Chạy phân tích so sánh vi phân các phiên
        diff_res = await self.diff_use_case.execute(task_id)

        # 2. Đọc thông tin target request từ cơ sở dữ liệu
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(NetworkRequestModel).where(
                NetworkRequestModel.id == target_request_id
            )
            req_row = (await db.execute(stmt)).scalar_one_or_none()

        if not req_row:
            # Fallback nếu truyền req_id dạng rút gọn
            async with self.session_factory() as db:
                stmt = select(NetworkRequestModel).where(
                    NetworkRequestModel.id.like(f"%{target_request_id}%")
                )
                req_row = (await db.execute(stmt)).scalar_one_or_none()

        if not req_row:
            raise ValueError(f"Target request '{target_request_id}' not found")

        method = req_row.method
        url = req_row.url
        headers = safe_loads(req_row.headers_json) if req_row.headers_json else {}
        body = safe_loads(req_row.body_json) if req_row.body_json else None

        # 3. Tạo template hóa cho Headers và Body dựa trên phân loại vi phân
        headers_template = {}
        body_template = body
        required_variables: list[str] = []
        session_prerequisites: list[ReplayStepSpec] = []
        param_lineages = {}

        # Phân tích Lineage cho request này
        lineage_path = await self.trace_use_case.trace_backward(
            session_id=req_row.session_id,
            target_node_id=req_row.id,
        )
        if lineage_path:
            param_lineages["request"] = lineage_path
            if lineage_path.origin_type == "storage" and lineage_path.origin_key:
                # Tạo bước tiền đề đọc storage
                session_prerequisites.append(
                    ReplayStepSpec(
                        order=1,
                        step_type="read_storage",
                        target_id=lineage_path.origin_node_id,
                        action=f"localStorage.getItem('{lineage_path.origin_key}')",
                        output_bindings={lineage_path.origin_key: lineage_path.origin_key},
                    )
                )

        # Xây dựng Template cho headers
        for h_key, h_val in headers.items():
            h_key_lower = h_key.lower()
            if "auth" in h_key_lower or "token" in h_key_lower:
                headers_template[h_key] = "Bearer {{auth_token}}"
            else:
                headers_template[h_key] = h_val

        # Xây dựng Template cho body
        if isinstance(body, str) and (body.strip().startswith("{") or body.strip().startswith("[")):
            try:
                body = json.loads(body)
            except Exception:
                pass

        if isinstance(body, dict):
            body_template = dict(body)
            for v_path in diff_res.classified_variables:
                field_name = v_path.replace("body.", "")
                if field_name in body_template:
                    body_template[field_name] = f"{{{{{field_name}}}}}"
                    required_variables.append(field_name)

        return ReplaySpec(
            task_id=task_id,
            target_request_id=req_row.id,
            method=method,
            url_template=url,
            headers_template=headers_template,
            body_template=body_template,
            required_variables=required_variables,
            session_prerequisites=session_prerequisites,
            parameter_lineages=param_lineages,
            metadata={
                "session_count": len(diff_res.session_ids),
                "summary": diff_res.summary,
            },
        )
