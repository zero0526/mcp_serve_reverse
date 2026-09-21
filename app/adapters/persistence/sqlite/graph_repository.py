from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    EdgeEvidenceModel,
    GraphEdgeModel,
    GraphNodeModel,
)
from app.domain.graph.edges import EdgeEvidence, GraphEdge
from app.domain.graph.nodes import GraphNode
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from app.ports.graph_repository import GraphRepositoryPort


class SQLiteGraphRepository(GraphRepositoryPort):
    """Adapter thao tác với bảng graph_nodes, graph_edges, edge_evidence trong SQLite."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def save_nodes(self, nodes: list[GraphNode]) -> None:
        """Lưu danh sách node, hỗ trợ upsert nếu node_id đã tồn tại."""
        if not nodes:
            return

        async with self.session_factory() as db:  # type: AsyncSession
            for node in nodes:
                node_type_val = (
                    node.node_type.value
                    if hasattr(node.node_type, "value")
                    else str(node.node_type)
                )
                existing = (
                    await db.execute(
                        select(GraphNodeModel).where(GraphNodeModel.id == node.id)
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.session_id = node.session_id
                    existing.node_type = node_type_val
                    existing.label = node.label
                    existing.entity_id = node.entity_id
                    existing.properties_json = safe_dumps(node.properties)
                else:
                    rec = GraphNodeModel(
                        id=node.id,
                        session_id=node.session_id,
                        node_type=node_type_val,
                        label=node.label,
                        entity_id=node.entity_id,
                        properties_json=safe_dumps(node.properties),
                        created_at_ns=node.created_at_ns,
                    )
                    db.add(rec)
            await db.commit()

    async def save_edges(self, edges: list[GraphEdge]) -> None:
        """Lưu danh sách edges và evidence đi kèm, phòng chống duplicate."""
        if not edges:
            return

        async with self.session_factory() as db:  # type: AsyncSession
            for edge in edges:
                rel_val = (
                    edge.relation_type.value
                    if hasattr(edge.relation_type, "value")
                    else str(edge.relation_type)
                )

                # Kiểm tra edge đã tồn tại chưa
                stmt = select(GraphEdgeModel).where(
                    GraphEdgeModel.session_id == edge.session_id,
                    GraphEdgeModel.source_id == edge.source_id,
                    GraphEdgeModel.target_id == edge.target_id,
                    GraphEdgeModel.relation_type == rel_val,
                )
                existing = (await db.execute(stmt)).scalar_one_or_none()

                if existing:
                    existing.confidence = edge.confidence
                    existing.provenance_status = edge.provenance_status
                    existing.properties_json = safe_dumps(edge.properties)
                    edge_db_id = existing.id
                else:
                    edge_rec = GraphEdgeModel(
                        session_id=edge.session_id,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        relation_type=rel_val,
                        confidence=edge.confidence,
                        provenance_status=edge.provenance_status,
                        properties_json=safe_dumps(edge.properties),
                        created_at_ns=edge.created_at_ns,
                    )
                    db.add(edge_rec)
                    await db.flush()
                    edge_db_id = edge_rec.id

                # Thêm evidence
                for ev in edge.evidence_list:
                    ev_rec = EdgeEvidenceModel(
                        edge_id=edge_db_id,
                        evidence_type=ev.evidence_type,
                        source_event_id=ev.source_event_id,
                        confidence=ev.confidence,
                        explanation=ev.explanation,
                        metadata_json=safe_dumps(ev.metadata),
                    )
                    db.add(ev_rec)

            await db.commit()

    async def get_node(self, node_id: str) -> GraphNode | None:
        async with self.session_factory() as db:
            stmt = select(GraphNodeModel).where(GraphNodeModel.id == node_id)
            res = await db.execute(stmt)
            obj = res.scalar_one_or_none()
            if not obj:
                return None
            return GraphNode(
                id=obj.id,
                session_id=obj.session_id,
                node_type=obj.node_type,
                label=obj.label,
                entity_id=obj.entity_id,
                properties=safe_loads(obj.properties_json),
                created_at_ns=obj.created_at_ns,
            )

    async def get_nodes(
        self,
        session_id: str,
        node_type: str | None = None,
    ) -> list[GraphNode]:
        async with self.session_factory() as db:
            stmt = select(GraphNodeModel).where(GraphNodeModel.session_id == session_id)
            if node_type:
                stmt = stmt.where(GraphNodeModel.node_type == node_type)
            res = await db.execute(stmt)
            records = res.scalars().all()

            return [
                GraphNode(
                    id=r.id,
                    session_id=r.session_id,
                    node_type=r.node_type,
                    label=r.label,
                    entity_id=r.entity_id,
                    properties=safe_loads(r.properties_json),
                    created_at_ns=r.created_at_ns,
                )
                for r in records
            ]

    def _to_graph_edge(self, r: GraphEdgeModel) -> GraphEdge:
        ev_list = [
            EdgeEvidence(
                id=ev.id,
                edge_id=ev.edge_id,
                evidence_type=ev.evidence_type,
                source_event_id=ev.source_event_id,
                confidence=ev.confidence,
                explanation=ev.explanation,
                metadata=safe_loads(ev.metadata_json),
            )
            for ev in (r.evidence_list or [])
        ]
        return GraphEdge(
            id=r.id,
            session_id=r.session_id,
            source_id=r.source_id,
            target_id=r.target_id,
            relation_type=r.relation_type,
            confidence=r.confidence,
            provenance_status=r.provenance_status,
            properties=safe_loads(r.properties_json),
            created_at_ns=r.created_at_ns,
            evidence_list=ev_list,
        )

    async def get_edges(
        self,
        session_id: str,
        relation_type: str | None = None,
    ) -> list[GraphEdge]:
        async with self.session_factory() as db:
            stmt = (
                select(GraphEdgeModel)
                .options(selectinload(GraphEdgeModel.evidence_list))
                .where(GraphEdgeModel.session_id == session_id)
            )
            if relation_type:
                stmt = stmt.where(GraphEdgeModel.relation_type == relation_type)
            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_graph_edge(r) for r in records]

    async def get_incoming_edges(self, target_node_id: str) -> list[GraphEdge]:
        async with self.session_factory() as db:
            stmt = (
                select(GraphEdgeModel)
                .options(selectinload(GraphEdgeModel.evidence_list))
                .where(GraphEdgeModel.target_id == target_node_id)
            )
            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_graph_edge(r) for r in records]

    async def get_outgoing_edges(self, source_node_id: str) -> list[GraphEdge]:
        async with self.session_factory() as db:
            stmt = (
                select(GraphEdgeModel)
                .options(selectinload(GraphEdgeModel.evidence_list))
                .where(GraphEdgeModel.source_id == source_node_id)
            )
            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_graph_edge(r) for r in records]
