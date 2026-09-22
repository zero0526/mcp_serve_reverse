from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.ports.graph_repository import GraphRepositoryPort


class TraceOriginUseCase:
    """Use case truy vết ngược nguồn gốc dữ liệu (Upstream Lineage Traversal)."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)
        self.trace_use_case = TraceLineageUseCase(self.graph_repo)

    async def execute(
        self,
        session_id: str,
        target_node_id: str,
        max_depth: int = 10,
        max_paths: int = 20,
        min_confidence: float = 0.8,
        include_heuristics: bool = False,
    ) -> dict[str, Any]:
        path = await self.trace_use_case.trace_backward(
            session_id=session_id,
            target_node_id=target_node_id,
        )

        nodes = await self.graph_repo.get_nodes(session_id)
        node_map = {n.id: n for n in nodes}
        target_node = node_map.get(target_node_id) or next((n for n in nodes if n.entity_id == target_node_id), None)

        paths = []
        if path and path.steps:
            steps = [
                {
                    "step_number": s.step_number,
                    "from_node_id": s.from_node_id,
                    "to_node_id": s.to_node_id,
                    "relation": s.relation,
                    "action_description": s.action_description,
                    "confidence": s.confidence,
                    "evidence_refs": s.evidence_refs,
                }
                for s in path.steps
            ]
            paths.append({
                "path_id": "path_001",
                "confidence": path.overall_confidence,
                "status": path.status,
                "origin_node_id": path.origin_node_id,
                "origin_type": path.origin_type,
                "origin_key": path.origin_key,
                "steps": steps,
            })

        return {
            "target": {
                "node_id": target_node.id if target_node else target_node_id,
                "label": target_node.label if target_node else target_node_id,
                "node_type": target_node.node_type if target_node else "UNKNOWN",
            },
            "paths": paths,
            "paths_found": len(paths),
            "paths_returned": len(paths),
            "truncated": False,
        }
