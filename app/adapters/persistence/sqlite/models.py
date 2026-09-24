from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.persistence.sqlite.connection import Base


class TaskModel(Base):
    """Bảng quản lý các nhiệm vụ phân tích đảo ngược (Tasks)."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    goal_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    env_vars_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    initial_urls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    browser_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="CREATED", index=True)

    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel", back_populates="task", cascade="all, delete-orphan"
    )
    logs: Mapped[list["SessionLogModel"]] = relationship(
        "SessionLogModel", back_populates="task", cascade="all, delete-orphan"
    )


class SessionModel(Base):
    """Bảng lưu các phiên capture (browser hoặc android)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    started_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ended_at_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)

    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    task: Mapped["TaskModel | None"] = relationship("TaskModel", back_populates="sessions")
    session_logs: Mapped[list["SessionLogModel"]] = relationship(
        "SessionLogModel", back_populates="session", cascade="all, delete-orphan"
    )
    trace_events: Mapped[list["TraceEventModel"]] = relationship(
        "TraceEventModel", back_populates="session", cascade="all, delete-orphan"
    )
    function_executions: Mapped[list["FunctionExecutionModel"]] = relationship(
        "FunctionExecutionModel", back_populates="session", cascade="all, delete-orphan"
    )
    network_requests: Mapped[list["NetworkRequestModel"]] = relationship(
        "NetworkRequestModel", back_populates="session", cascade="all, delete-orphan"
    )
    storage_operations: Mapped[list["StorageOperationModel"]] = relationship(
        "StorageOperationModel", back_populates="session", cascade="all, delete-orphan"
    )
    graph_nodes: Mapped[list["GraphNodeModel"]] = relationship(
        "GraphNodeModel", back_populates="session", cascade="all, delete-orphan"
    )
    graph_edges: Mapped[list["GraphEdgeModel"]] = relationship(
        "GraphEdgeModel", back_populates="session", cascade="all, delete-orphan"
    )


class SessionLogModel(Base):
    """Bảng lưu trữ nhật ký hồi cứu và đánh giá tiến hóa MCP tools của Agent."""

    __tablename__ = "session_logs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )

    log_type: Mapped[str] = mapped_column(Text, nullable=False, default="RETROSPECTIVE", index=True)
    agent_evaluation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    missing_tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    suggested_tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bottlenecks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    efficiency_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="logs")
    session: Mapped["SessionModel | None"] = relationship("SessionModel", back_populates="session_logs")


class TraceEventModel(Base):
    """Nguồn dữ liệu gốc lưu mọi event sau khi chuẩn hóa."""

    __tablename__ = "trace_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="browser")
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)

    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    execution_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    parent_execution_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    payload_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="trace_events")

    __table_args__ = (
        Index("idx_events_session_time", "session_id", "timestamp_ns"),
        Index("idx_events_type_time", "event_type", "timestamp_ns"),
        Index("idx_events_execution", "execution_id"),
    )


class FunctionExecutionModel(Base):
    """Lần thực thi hàm (function call / return / throw)."""

    __tablename__ = "function_executions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    function_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    module_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_location: Mapped[str | None] = mapped_column(Text, nullable=True)

    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_execution_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ended_at_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    arguments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_value_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="function_executions")


class NetworkRequestModel(Base):
    """HTTP request được quan sát."""

    __tablename__ = "network_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("trace_events.event_id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    method: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    host: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    body_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    resource_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiator_type: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="network_requests")
    response: Mapped["NetworkResponseModel | None"] = relationship(
        "NetworkResponseModel", back_populates="request", uselist=False, cascade="all, delete-orphan"
    )


class NetworkResponseModel(Base):
    """HTTP response tương ứng với request."""

    __tablename__ = "network_responses"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("trace_events.event_id", ondelete="SET NULL"), nullable=True
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    body_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    body_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    request: Mapped["NetworkRequestModel"] = relationship("NetworkRequestModel", back_populates="response")


class ValueObservationModel(Base):
    """Giá trị độc lập phục vụ Data Lineage."""

    __tablename__ = "value_observations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    value_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    value_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    variable_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    sensitivity: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    redacted_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class GraphNodeModel(Base):
    """Node trong Property Graph."""

    __tablename__ = "graph_nodes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    node_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    properties_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="graph_nodes")

    __table_args__ = (
        Index("idx_graph_nodes_session_type", "session_id", "node_type"),
        Index("idx_graph_nodes_entity", "session_id", "entity_id"),
    )


class GraphEdgeModel(Base):
    """Edge trong Property Graph biểu diễn quan hệ giữa các Node."""

    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        Text, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False
    )

    relation_type: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    provenance_status: Mapped[str] = mapped_column(Text, nullable=False)

    properties_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="graph_edges")
    evidence_list: Mapped[list["EdgeEvidenceModel"]] = relationship(
        "EdgeEvidenceModel", back_populates="edge", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_edges_source_relation", "source_id", "relation_type"),
        Index("idx_edges_target_relation", "target_id", "relation_type"),
        Index("idx_edges_session_relation", "session_id", "relation_type"),
        Index("idx_edges_confidence", "confidence"),
        UniqueConstraint("session_id", "source_id", "target_id", "relation_type", name="uq_graph_edge"),
    )


class EdgeEvidenceModel(Base):
    """Bằng chứng chứng minh cho quan hệ của Graph Edge."""

    __tablename__ = "edge_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("graph_edges.id", ondelete="CASCADE"), nullable=False, index=True
    )

    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("trace_events.event_id", ondelete="SET NULL"), nullable=True
    )

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    edge: Mapped["GraphEdgeModel"] = relationship("GraphEdgeModel", back_populates="evidence_list")


class StorageOperationModel(Base):
    """Thao tác đọc / ghi / xóa storage (localStorage, sessionStorage, cookie)."""

    __tablename__ = "storage_operations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("trace_events.event_id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    storage_type: Mapped[str] = mapped_column(Text, nullable=False)
    storage_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    operation: Mapped[str] = mapped_column(Text, nullable=False)
    value_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    timestamp_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="storage_operations")

    __table_args__ = (
        Index("idx_storage_session_key", "session_id", "storage_key"),
    )


class ReplayPlanModel(Base):
    """Kế hoạch replay workflow hoặc request."""

    __tablename__ = "replay_plans"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_request_id: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    policy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    steps: Mapped[list["ReplayStepModel"]] = relationship(
        "ReplayStepModel", back_populates="plan", cascade="all, delete-orphan"
    )


class ReplayStepModel(Base):
    """Từng bước thực thi trong Replay Plan."""

    __tablename__ = "replay_steps"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    replay_plan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("replay_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(Text, nullable=False)

    target_node_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    plan: Mapped["ReplayPlanModel"] = relationship("ReplayPlanModel", back_populates="steps")

    __table_args__ = (
        Index("idx_replay_steps_plan_order", "replay_plan_id", "step_order"),
    )
