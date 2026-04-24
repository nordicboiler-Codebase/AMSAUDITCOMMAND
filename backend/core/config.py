from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg2://audit:audit@localhost:5432/audit",
        alias="DATABASE_URL",
    )
    secret_key: str = Field(default="dev-secret", alias="SECRET_KEY")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=480, alias="JWT_EXPIRE_MINUTES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / "parquet"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.parquet_dir, self.reports_dir, self.reference_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
