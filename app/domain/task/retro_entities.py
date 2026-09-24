from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class LogType(str, Enum):
    RETROSPECTIVE = "RETROSPECTIVE"
    TOOL_CRITIQUE = "TOOL_CRITIQUE"
    EXECUTION_TRACE = "EXECUTION_TRACE"
    ERROR = "ERROR"


class ToolProposal(BaseModel):
    name: str
    purpose: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = ""


class SessionLog(BaseModel):
    id: str
    task_id: str
    session_id: str | None = None
    log_type: LogType = LogType.RETROSPECTIVE
    agent_evaluation: str
    missing_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[ToolProposal | dict[str, Any]] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    efficiency_rating: int = 5
    created_at_ns: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
