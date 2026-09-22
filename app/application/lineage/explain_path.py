from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.ports.graph_repository import GraphRepositoryPort


class ExplainLineagePathUseCase:
    """Use case diễn giải đường dẫn Lineage thành dạng con người / LLM dễ đọc."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)
        self.trace_use_case = TraceLineageUseCase(self.graph_repo)

    async def execute(
        self,
        session_id: str,
        target_node_id: str,
        path_id: str | None = None,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        node_map = {n.id: n for n in nodes}
        target_node = node_map.get(target_node_id) or next((n for n in nodes if n.entity_id == target_node_id), None)

        if not target_node:
            return {
                "summary": f"Không tìm thấy node {target_node_id} trong session {session_id}",
                "steps": [],
                "unknowns": ["Node không tồn tại trong đồ thị"],
            }

        path = await self.trace_use_case.trace_backward(
            session_id=session_id,
            target_node_id=target_node.id,
        )

        if not path or not path.steps:
            return {
                "summary": f"Node '{target_node.label}' không có liên kết nguồn gốc nào được ghi nhận.",
                "steps": [],
                "unknowns": ["Không tìm thấy vết dữ liệu trước đó"],
            }

        steps = []
        unknowns = []

        for s in path.steps:
            s_node = node_map.get(s.from_node_id)
            t_node = node_map.get(s.to_node_id)
            s_label = s_node.label if s_node else s.from_node_id
            t_label = t_node.label if t_node else s.to_node_id

            steps.append({
                "order": s.step_number,
                "operation": s.relation,
                "description": s.action_description,
                "confidence": s.confidence,
                "source_node": s_label,
                "target_node": t_label,
                "evidence": s.evidence_refs,
            })

        summary = (
            f"Node mục tiêu '{target_node.label}' bắt nguồn từ '{path.origin_type}' (key: {path.origin_key}) "
            f"qua {len(steps)} bước chuyển tiếp với độ tin cậy tổng thể {path.overall_confidence}."
        )

        return {
            "summary": summary,
            "target": target_node.label,
            "steps": steps,
            "unknowns": unknowns or ["Không có cảnh báo dữ liệu"],
        }
