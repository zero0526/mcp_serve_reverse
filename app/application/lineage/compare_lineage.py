from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.ports.graph_repository import GraphRepositoryPort


class CompareLineageUseCase:
    """Use case so sánh hai đường dẫn Lineage hoặc hai session khác nhau."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)
        self.trace_use_case = TraceLineageUseCase(self.graph_repo)

    async def execute(
        self,
        left_session_id: str,
        left_node_id: str,
        right_session_id: str,
        right_node_id: str,
        comparison_mode: str = "structure",
    ) -> dict[str, Any]:
        left_path = await self.trace_use_case.trace_backward(
            session_id=left_session_id,
            target_node_id=left_node_id,
        )
        right_path = await self.trace_use_case.trace_backward(
            session_id=right_session_id,
            target_node_id=right_node_id,
        )

        differences = []
        if not left_path:
            differences.append(f"Left target '{left_node_id}' không có lineage chain.")
        if not right_path:
            differences.append(f"Right target '{right_node_id}' không có lineage chain.")

        origins_match = False
        step_diff = 0
        similarity = 0.0

        if left_path and right_path:
            origins_match = left_path.origin_type == right_path.origin_type and left_path.origin_key == right_path.origin_key
            step_diff = len(left_path.steps) - len(right_path.steps)

            if not origins_match:
                differences.append(
                    f"Nguồn gốc khác nhau: Left ({left_path.origin_type}:{left_path.origin_key}) vs Right ({right_path.origin_type}:{right_path.origin_key})"
                )

            left_rels = [s.relation for s in left_path.steps]
            right_rels = [s.relation for s in right_path.steps]

            set_l = set(left_rels)
            set_r = set(right_rels)
            union_len = len(set_l.union(set_r))
            similarity = round(len(set_l.intersection(set_r)) / union_len, 2) if union_len > 0 else 1.0

            if left_rels != right_rels:
                differences.append(f"Chuỗi quan hệ khác nhau: Left {left_rels} vs Right {right_rels}")

        return {
            "comparison_mode": comparison_mode,
            "origins_match": origins_match,
            "step_difference": step_diff,
            "structural_similarity": similarity,
            "differences": differences,
            "left": {
                "session_id": left_session_id,
                "node_id": left_node_id,
                "steps_count": len(left_path.steps) if left_path else 0,
            },
            "right": {
                "session_id": right_session_id,
                "node_id": right_node_id,
                "steps_count": len(right_path.steps) if right_path else 0,
            },
        }
