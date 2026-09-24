from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base Paths
    base_dir: Path = BASE_DIR
    data_dir: Path = Field(default_factory=lambda: BASE_DIR / "data")
    database_dir: Path = Field(default_factory=lambda: BASE_DIR / "data" / "database")
    sessions_dir: Path = Field(default_factory=lambda: BASE_DIR / "data" / "sessions")
    secrets_dir: Path = Field(default_factory=lambda: BASE_DIR / "data" / "secrets")

    OVERSIZE_THRESHOLD: int = 16384
    # Database
    db_file_name: str = "lineage.db"

    @property
    def db_path(self) -> Path:
        return self.database_dir / self.db_file_name

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def async_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
