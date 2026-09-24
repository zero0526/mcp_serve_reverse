"""Cấu hình cho Playground Backend API Server."""

import os
from pydantic_settings import BaseSettings


class BackendSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ]


settings = BackendSettings()
