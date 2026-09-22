from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.ports.graph_repository import GraphRepositoryPort


class AnalyzeRequestLineageUseCase:
    """Use case phân tích toàn diện nguồn gốc các tham số cấu thành một HTTP Request."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        session_id: str,
        request_id: str,
        min_confidence: float = 0.8,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        edges = await self.graph_repo.get_edges(session_id)
        node_map = {n.id: n for n in nodes}

        # Find target request node
        req_node = next(
            (
                n
                for n in nodes
                if n.node_type == NodeType.HTTP_REQUEST
                and (n.id == request_id or n.entity_id == request_id or request_id in (n.entity_id or ""))
            ),
            None,
        )
        if not req_node:
            return {"request_id": request_id, "parameters": [], "sources": []}

        # Find all edges pointing to req_node
        inbound_edges = [e for e in edges if e.target_id == req_node.id and e.confidence >= min_confidence]

        parameters = []
        sources = []

        for e in inbound_edges:
            s_node = node_map.get(e.source_id)
            if not s_node:
                continue

            if e.relation_type == RelationType.READS_FROM:
                parameters.append({
                    "location": f"storage.{s_node.properties.get('storage_key')}",
                    "source": s_node.label,
                    "source_type": s_node.node_type,
                    "relation": e.relation_type,
                    "lineage_status": e.provenance_status.upper(),
                    "confidence": e.confidence,
                })
                sources.append({"type": "STORAGE", "name": s_node.label, "confidence": e.confidence})

            elif e.relation_type == RelationType.USED_IN:
                parameters.append({
                    "location": s_node.properties.get("path", "param"),
                    "value": s_node.properties.get("value"),
                    "source": s_node.label,
                    "source_type": s_node.node_type,
                    "relation": e.relation_type,
                    "lineage_status": e.provenance_status.upper(),
                    "confidence": e.confidence,
                })

            elif e.relation_type == RelationType.CALLS:
                sources.append({"type": "FUNCTION_DISPATCHER", "name": s_node.label, "confidence": e.confidence})
                # Check if this function has crypto operations
                crypto_edges = [ce for ce in edges if ce.source_id == s_node.id and ce.relation_type == RelationType.TRANSFORMS]
                for ce in crypto_edges:
                    c_node = node_map.get(ce.target_id)
                    if c_node:
                        sources.append({
                            "type": "CRYPTO_TRANSFORMATION",
                            "name": c_node.label,
                            "algorithm": c_node.properties.get("algorithm"),
                            "confidence": ce.confidence,
                        })

        return {
            "request_id": req_node.entity_id or req_node.id,
            "request_url": req_node.properties.get("url"),
            "method": req_node.properties.get("method"),
            "parameters": parameters,
            "sources": sources,
            "inbound_evidence_count": len(inbound_edges),
        }
