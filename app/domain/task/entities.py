from enum import Enum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EnvVarLocation(str, Enum):
    HEADER = "header"  # Gắn vào HTTP Request Headers
    URL = "url"        # Gắn vào Param trên URL (query string)
    BODY = "body"      # Gắn vào thành phần payload trong Request Body (JSON/form)


class EnvVarItem(BaseModel):
    name: str = Field(..., description="Tên thuộc tính / key của biến môi trường")
    value: Any = Field(..., description="Giá trị của biến")
    location: EnvVarLocation = Field(
        default=EnvVarLocation.HEADER,
        description="Vị trí gắn vào: 'header', 'url' (param trên URL), hoặc 'body' (thành phần trong body)",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Cho phép dùng 'key' thay cho 'name'
            if "name" not in data and "key" in data:
                data["name"] = data["key"]
            # Chuẩn hóa location linh hoạt
            raw_loc = str(
                data.get("location") or data.get("position") or data.get("target") or "header"
            ).lower().strip()
            if raw_loc in ("url", "param", "params", "query", "query_param", "url_param"):
                data["location"] = EnvVarLocation.URL
            elif raw_loc in ("body", "json", "payload", "data"):
                data["location"] = EnvVarLocation.BODY
            else:
                data["location"] = EnvVarLocation.HEADER
        return data


def parse_env_vars(env_vars: Any) -> list[EnvVarItem]:
    """Parse đa dạng các định dạng env_vars sang danh sách chuẩn EnvVarItem.

    Hỗ trợ:
    - Danh sách EnvVarItem hoặc dict: [{"name": "X", "value": "Y", "location": "header"}]
    - Dict key-value: {"API_KEY": "123", "TOKEN": "abc"}
    - Dict nested config: {"API_KEY": {"value": "123", "location": "url"}}
    """
    if not env_vars:
        return []

    if isinstance(env_vars, list):
        items: list[EnvVarItem] = []
        for x in env_vars:
            if isinstance(x, EnvVarItem):
                items.append(x)
            elif isinstance(x, dict):
                items.append(EnvVarItem(**x))
        return items

    if isinstance(env_vars, dict):
        items = []
        for k, v in env_vars.items():
            if isinstance(v, dict):
                items.append(EnvVarItem(name=k, **v))
            elif isinstance(v, EnvVarItem):
                items.append(v)
            else:
                items.append(EnvVarItem(name=k, value=v, location=EnvVarLocation.HEADER))
        return items

    return []


def append_query_params(url: str, params: dict[str, Any]) -> str:
    """Gắn hoặc cập nhật query parameters vào URL."""
    if not params or not url:
        return url
    parsed = urlparse(url)
    existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for k, v in params.items():
        existing_params[str(k)] = str(v)
    new_query = urlencode(existing_params)
    return urlunparse(parsed._replace(query=new_query))


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
    env_vars: dict[str, Any] | list[Any] = Field(default_factory=dict)
    env_vars_items: list[EnvVarItem] = Field(default_factory=list)
    initial_urls: list[str] = Field(default_factory=list)
    browser_config: BrowserConfig = Field(default_factory=BrowserConfig)
    status: TaskStatus = TaskStatus.CREATED
    session_ids: list[str] = Field(default_factory=list)
    created_at_ns: int = 0
    updated_at_ns: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_env_vars_consistency(self) -> "Task":
        if not self.env_vars_items and self.env_vars:
            self.env_vars_items = parse_env_vars(self.env_vars)
        if isinstance(self.env_vars, list):
            self.env_vars = {item.name: item.value for item in self.env_vars_items}
        return self

    @property
    def parsed_env_vars(self) -> list[EnvVarItem]:
        """Trả về danh sách các đối tượng EnvVarItem chuẩn hóa."""
        return self.env_vars_items or parse_env_vars(self.env_vars)

    def get_env_headers(self) -> dict[str, str]:
        """Trích xuất các biến môi trường được gắn vào Request Header."""
        return {item.name: str(item.value) for item in self.parsed_env_vars if item.location == EnvVarLocation.HEADER}

    def get_env_url_params(self) -> dict[str, str]:
        """Trích xuất các biến môi trường được gắn vào Param trên URL (query parameter)."""
        return {item.name: str(item.value) for item in self.parsed_env_vars if item.location == EnvVarLocation.URL}

    def get_env_body_params(self) -> dict[str, Any]:
        """Trích xuất các biến môi trường được gắn vào thành phần payload trong Request Body."""
        return {item.name: item.value for item in self.parsed_env_vars if item.location == EnvVarLocation.BODY}

