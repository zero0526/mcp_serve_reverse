from typing import Any

from app.domain.graph.relations import RelationType
from app.domain.lineage.entities import LineagePath, LineageStep
from app.ports.graph_repository import GraphRepositoryPort


class TraceLineageUseCase:
    """Use case thực hiện truy vết nguồn gốc (backward) và lan truyền (forward) trên Property Graph."""

    def __init__(self, graph_repository: GraphRepositoryPort):
        self.graph_repo = graph_repository

    async def trace_backward(
        self,
        session_id: str,
        target_node_id: str,
        param_name: str | None = None,
    ) -> LineagePath | None:
        """Lần ngược đồ thị từ một Request Node để tìm nguồn gốc sinh ra tham số."""
        target_node = await self.graph_repo.get_node(target_node_id)
        if not target_node:
            # Thử tìm theo entity_id nếu người dùng truyền request_id thuần túy
            nodes = await self.graph_repo.get_nodes(session_id)
            for n in nodes:
                if n.entity_id == target_node_id or n.id == f"node_req_{target_node_id}":
                    target_node = n
                    target_node_id = n.id
                    break

        if not target_node:
            return None

        incoming_edges = await self.graph_repo.get_incoming_edges(target_node_id)

        # Lọc các cạnh liên quan đến luồng dữ liệu (READS_FROM, USED_IN)
        data_edges = [
            e for e in incoming_edges
            if e.relation_type in [RelationType.READS_FROM.value, RelationType.USED_IN.value]
        ]

        steps: list[LineageStep] = []
        origin_node_id = target_node_id
        origin_type = "unknown"
        origin_key = None
        overall_conf = 1.0

        for i, edge in enumerate(data_edges, start=1):
            source_node = await self.graph_repo.get_node(edge.source_id)
            s_label = source_node.label if source_node else edge.source_id
            s_type = source_node.node_type if source_node else "unknown"

            # Nếu lọc theo param_name cụ thể (ví dụ: "authorization" hay "auth_token")
            if param_name:
                key = str(edge.properties.get("storage_key") or edge.properties.get("path") or "").lower()
                if param_name.lower() not in key and key not in param_name.lower():
                    continue

            action_desc = f"Read data from {s_label} into request"
            if edge.relation_type == RelationType.USED_IN.value:
                action_desc = f"Directly used value at {edge.properties.get('path', '')}"

            evidence_refs = [
                ev.explanation or ev.evidence_type for ev in edge.evidence_list
            ]

            step = LineageStep(
                step_number=i,
                from_node_id=edge.source_id,
                to_node_id=target_node_id,
                relation=edge.relation_type,
                action_description=action_desc,
                confidence=edge.confidence,
                evidence_refs=evidence_refs,
            )
            steps.append(step)

            if origin_node_id == target_node_id:
                origin_node_id = edge.source_id
                origin_type = "storage" if "stor" in edge.source_id else str(s_type)
                origin_key = edge.properties.get("storage_key") or edge.properties.get("path")
                overall_conf = edge.confidence

        if not steps:
            # Không tìm thấy nguồn gốc qua storage, coi như user input hoặc hardcoded
            return LineagePath(
                target_node_id=target_node_id,
                target_param=param_name or "request_payload",
                origin_node_id=target_node_id,
                origin_type="user_input_or_constant",
                origin_key=param_name,
                steps=[],
                overall_confidence=0.8,
                status="SUPPORTED_INFERENCE",
            )

        return LineagePath(
            target_node_id=target_node_id,
            target_param=param_name or (origin_key or "payload"),
            origin_node_id=origin_node_id,
            origin_type=origin_type,
            origin_key=origin_key,
            steps=steps,
            overall_confidence=overall_conf,
            status="CONFIRMED" if overall_conf >= 0.9 else "SUPPORTED_INFERENCE",
        )

    async def trace_forward(
        self,
        session_id: str,
        origin_node_id: str,
    ) -> list[LineagePath]:
        """Truy vết xuôi xem từ một Node nguồn (Storage / Response) dữ liệu chảy tới đâu."""
        outgoing_edges = await self.graph_repo.get_outgoing_edges(origin_node_id)
        paths: list[LineagePath] = []

        for i, edge in enumerate(outgoing_edges, start=1):
            target_node = await self.graph_repo.get_node(edge.target_id)
            t_label = target_node.label if target_node else edge.target_id

            step = LineageStep(
                step_number=1,
                from_node_id=origin_node_id,
                to_node_id=edge.target_id,
                relation=edge.relation_type,
                action_description=f"Propagated to {t_label}",
                confidence=edge.confidence,
                evidence_refs=[ev.explanation or ev.evidence_type for ev in edge.evidence_list],
            )

            path = LineagePath(
                target_node_id=edge.target_id,
                target_param=edge.properties.get("storage_key") or "propagated_value",
                origin_node_id=origin_node_id,
                origin_type="storage",
                origin_key=edge.properties.get("storage_key"),
                steps=[step],
                overall_confidence=edge.confidence,
                status="CONFIRMED",
            )
            paths.append(path)

        return paths
