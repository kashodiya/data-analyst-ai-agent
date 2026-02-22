"""Configuration settings for the Data Analytics Agent."""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM Configuration
    llm_base_url: str
    llm_api_key: str
    llm_model: str = "claude4.5"

    # Database Configuration
    database_path: str = "../data/sessions.db"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["*"]

    # Logging
    log_level: str = "INFO"

    # Agent Configuration
    max_sql_results: int = 100
    sql_query_timeout: int = 30
    max_message_history: int = 50

    @property
    def database_url(self) -> str:
        """Get the SQLAlchemy database URL."""
        db_path = Path(self.database_path).resolve()
        return f"sqlite+aiosqlite:///{db_path}"


# Create a singleton settings instance
settings = Settings()