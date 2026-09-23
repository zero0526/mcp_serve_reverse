from typing import Any
from urllib.parse import urlparse

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.domain.graph.edges import EdgeEvidence, GraphEdge
from app.domain.graph.nodes import GraphNode, NodeType
from app.domain.graph.relations import RelationType
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope
from app.ports.graph_repository import GraphRepositoryPort


class ProjectEventUseCase:
    """Use case chiếu tức thì từng event vào Property Graph (Streaming / Incremental Projection)."""

    def __init__(
        self,
        graph_repository: GraphRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.graph_repo = graph_repository or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        event: EventEnvelope,
        normalized: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = event.session_id
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        sess_node_id = f"node_sess_{session_id}"
        # Đảm bảo Session node tồn tại
        sess_node = GraphNode(
            id=sess_node_id,
            session_id=session_id,
            node_type=NodeType.SESSION,
            label=f"Session {session_id}",
            entity_id=session_id,
            properties={"session_id": session_id},
        )
        nodes.append(sess_node)

        ev_type = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )
        if ev_type.startswith("EventType."):
            ev_type = ev_type.split(".", 1)[1].lower()

        payload = event.payload or {}
        metadata = event.metadata or {}

        # 1. NETWORK REQUEST
        if ev_type == EventType.NETWORK_REQUEST.value:
            req_id = payload.get("request_id") or event.event_id
            rnode_id = f"node_req_{session_id}_{req_id}"
            method = payload.get("method", "GET")
            url = payload.get("url", "")
            path = payload.get("path") or urlparse(url).path

            rnode = GraphNode(
                id=rnode_id,
                session_id=session_id,
                node_type=NodeType.HTTP_REQUEST,
                label=f"{method} {path or url}",
                entity_id=req_id,
                properties={
                    "request_id": req_id,
                    "method": method,
                    "url": url,
                    "path": path,
                    "headers": payload.get("headers", {}),
                    "query": payload.get("query", {}),
                    "body": payload.get("body") or payload.get("post_data"),
                    "resource_type": payload.get("resource_type"),
                    "started_at_ns": event.timestamp_ns,
                },
            )
            nodes.append(rnode)

            # Session CONTAINS Request
            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=sess_node_id,
                    target_id=rnode_id,
                    relation_type=RelationType.CONTAINS,
                    confidence=1.0,
                    provenance_status="observed",
                )
            )

            # Nếu có execution_id (từ JS call stack)
            if event.execution_id:
                fn_node_id = f"node_fn_{session_id}_{event.execution_id}"
                fn_node = GraphNode(
                    id=fn_node_id,
                    session_id=session_id,
                    node_type=NodeType.FUNCTION_EXECUTION,
                    label=metadata.get("function_name") or "In-Page Caller",
                    entity_id=event.execution_id,
                    properties={
                        "execution_id": event.execution_id,
                        "stack": metadata.get("stack") or metadata.get("stack_trace"),
                    },
                )
                nodes.append(fn_node)
                # Function CALLS Request
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        source_id=fn_node_id,
                        target_id=rnode_id,
                        relation_type=RelationType.CALLS,
                        confidence=0.95,
                        provenance_status="observed",
                        evidence_list=[
                            EdgeEvidence(
                                evidence_type="js_call_stack",
                                source_event_id=event.event_id,
                                confidence=0.95,
                                explanation="Function triggered network request",
                            )
                        ],
                    )
                )

        # 2. NETWORK RESPONSE
        elif ev_type == EventType.NETWORK_RESPONSE.value:
            req_id = payload.get("request_id") or "unknown_req"
            res_id = f"res_{event.event_id}"
            res_node_id = f"node_res_{session_id}_{res_id}"
            status_code = payload.get("status_code", 200)

            res_node = GraphNode(
                id=res_node_id,
                session_id=session_id,
                node_type=NodeType.HTTP_RESPONSE,
                label=f"Response {status_code}",
                entity_id=res_id,
                properties={
                    "response_id": res_id,
                    "request_id": req_id,
                    "status_code": status_code,
                    "headers": payload.get("headers", {}),
                    "body": payload.get("body"),
                },
            )
            nodes.append(res_node)

            # Request ASSOCIATED_WITH Response
            rnode_id = f"node_req_{session_id}_{req_id}"
            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=rnode_id,
                    target_id=res_node_id,
                    relation_type=RelationType.ASSOCIATED_WITH,
                    confidence=1.0,
                    provenance_status="observed",
                    evidence_list=[
                        EdgeEvidence(
                            evidence_type="network_correlation",
                            source_event_id=event.event_id,
                            confidence=1.0,
                            explanation=f"Request {req_id} matched response {res_id}",
                        )
                    ],
                )
            )

        # 3. STORAGE OPERATIONS
        elif ev_type in [
            EventType.STORAGE_READ.value,
            EventType.STORAGE_WRITE.value,
            EventType.STORAGE_DELETE.value,
            EventType.STORAGE_CLEAR.value,
        ]:
            stype = payload.get("storage_type", "local_storage")
            skey = payload.get("storage_key", "*all*")
            node_key = f"{stype}:{skey}"
            snode_id = f"node_stor_{session_id}_{stype}_{abs(hash(skey)) % 1000000}"

            snode = GraphNode(
                id=snode_id,
                session_id=session_id,
                node_type=NodeType.STORAGE_ENTRY,
                label=f"{stype}.{skey}",
                entity_id=node_key,
                properties={
                    "storage_type": stype,
                    "storage_key": skey,
                    "last_value_ref": payload.get("value_preview"),
                    "operation": payload.get("operation"),
                },
            )
            nodes.append(snode)

            # Session CONTAINS Storage Node
            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=sess_node_id,
                    target_id=snode_id,
                    relation_type=RelationType.CONTAINS,
                    confidence=1.0,
                    provenance_status="observed",
                )
            )

        # 4. FUNCTION EXECUTION
        elif ev_type in [EventType.FUNCTION_CALL.value, EventType.FUNCTION_RETURN.value]:
            exec_id = event.execution_id or event.event_id
            fn_node_id = f"node_fn_{session_id}_{exec_id}"
            fn_name = payload.get("function_name") or metadata.get("function_name") or "AnonymousFn"

            fn_node = GraphNode(
                id=fn_node_id,
                session_id=session_id,
                node_type=NodeType.FUNCTION_EXECUTION,
                label=f"fn {fn_name}",
                entity_id=exec_id,
                properties={
                    "execution_id": exec_id,
                    "function_name": fn_name,
                    "module": payload.get("module_name"),
                    "arguments": payload.get("arguments"),
                    "return_value": payload.get("return_value_ref"),
                },
            )
            nodes.append(fn_node)

            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=sess_node_id,
                    target_id=fn_node_id,
                    relation_type=RelationType.CONTAINS,
                    confidence=1.0,
                    provenance_status="observed",
                )
            )

            # Parent CALLS Child
            if event.parent_execution_id:
                parent_id = f"node_fn_{session_id}_{event.parent_execution_id}"
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        source_id=parent_id,
                        target_id=fn_node_id,
                        relation_type=RelationType.CALLS,
                        confidence=1.0,
                        provenance_status="observed",
                    )
                )

        # 5. CRYPTO OPERATION
        elif ev_type == EventType.CRYPTO_OPERATION.value:
            op_id = payload.get("operation_id") or event.event_id
            algo = payload.get("algorithm") or "unknown_algo"
            cnode_id = f"node_crypto_{session_id}_{op_id}"

            cnode = GraphNode(
                id=cnode_id,
                session_id=session_id,
                node_type=NodeType.CRYPTO_OPERATION,
                label=f"Crypto {algo}",
                entity_id=op_id,
                properties={
                    "operation_id": op_id,
                    "algorithm": algo,
                    "input_hash": payload.get("input_hash"),
                    "output_hash": payload.get("output_hash"),
                },
            )
            nodes.append(cnode)

            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=sess_node_id,
                    target_id=cnode_id,
                    relation_type=RelationType.CONTAINS,
                    confidence=1.0,
                    provenance_status="observed",
                )
            )

        if nodes:
            await self.graph_repo.save_nodes(nodes)
        if edges:
            await self.graph_repo.save_edges(edges)

        return {
            "session_id": session_id,
            "event_id": event.event_id,
            "event_type": ev_type,
            "nodes_projected": len(nodes),
            "edges_projected": len(edges),
        }
