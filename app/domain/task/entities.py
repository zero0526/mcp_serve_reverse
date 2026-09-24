from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BrowserConfig(BaseModel):
    headless: bool = False
    use_cloakbrowser: bool = False
    user_agent: str | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)
    pre_seed_storage: dict[str, Any] = Field(default_factory=dict)
    proxy: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 800


class Task(BaseModel):
    id: str
    name: str
    goal_description: str
    instructions: str
    env_vars: dict[str, Any] = Field(default_factory=dict)
    initial_urls: list[str] = Field(default_factory=list)
    browser_config: BrowserConfig = Field(default_factory=BrowserConfig)
    status: TaskStatus = TaskStatus.CREATED
    session_ids: list[str] = Field(default_factory=list)
    created_at_ns: int = 0
    updated_at_ns: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
