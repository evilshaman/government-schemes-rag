"""
Enterprise Configuration Management using pydantic-settings.
Centralizes environment variables, default configurations, security thresholds,
and path management across development, staging, and production environments.
"""

from __future__ import annotations
import os
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings for Government Schemes Discovery & RAG Platform.
    Loads from system environment variables and optional .env file.
    """

    # Environment & Deployment
    ENVIRONMENT: str = Field(default="production", description="Runtime environment: development, staging, production, test")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    PROJECT_NAME: str = Field(default="Government Schemes AI Discovery Engine", description="Application Name")
    VERSION: str = Field(default="5.0.0", description="API Version")
    API_V1_STR: str = Field(default="/api/v1", description="API prefix for v1 routes")
    
    # Server Binding
    HOST: str = Field(default="0.0.0.0", description="Host to bind server")
    PORT: int = Field(default=8000, description="Port to bind server")
    WORKERS: int = Field(default=4, description="Default number of Gunicorn/Uvicorn workers")
    
    # External LLM / Gemini API
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="API key for Google Gemini LLM")
    LLM_MODEL_NAME: str = Field(default="gemini-1.5-flash", description="Default LLM model name")
    LLM_TIMEOUT_SECONDS: int = Field(default=30, description="LLM call timeout in seconds")

    # Storage Paths
    BASE_DIR: str = Field(
        default_factory=lambda: os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    DB_PATH: str = Field(default="data/schemes_knowledge.db", description="Path to SQLite knowledge store")
    VECTOR_INDEX_PATH: str = Field(default="data/schemes_vector_index.json", description="Path to dense vector index")
    
    # Security & CORS
    SECRET_KEY: str = Field(
        default="gov-schemes-rag-production-insecure-secret-change-me",
        description="Application secret key for JWT/tokens/sessions"
    )
    CORS_ORIGINS: Union[List[str], str] = Field(
        default=["*"],
        description="Allowed CORS origins list or comma-separated string"
    )
    MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=15 * 1024 * 1024,  # 15 MB
        description="Maximum file upload size in bytes"
    )
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = Field(
        default=[".pdf", ".json", ".txt"],
        description="Allowed file extensions for GST or business profile uploads"
    )

    # Rate Limiting (slowapi)
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable or disable rate limiting")
    RATE_LIMIT_DEFAULT: str = Field(default="120/minute", description="Default global rate limit")
    RATE_LIMIT_ANALYZE: str = Field(default="30/minute", description="Rate limit for /api/reasoner/analyze")
    RATE_LIMIT_CHAT: str = Field(default="60/minute", description="Rate limit for /api/chat/ask")
    RATE_LIMIT_STORAGE_URL: str = Field(default="memory://", description="Rate limiter backend storage URI")

    # Observability & Metrics
    METRICS_ENABLED: bool = Field(default=True, description="Enable Prometheus/system metrics endpoint")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")

    # SQLite Concurrency & Pragma Tuning
    SQLITE_TIMEOUT_SECONDS: float = Field(default=10.0, description="SQLite busy connection timeout")
    SQLITE_BUSY_TIMEOUT_MS: int = Field(default=5000, description="SQLite busy_timeout PRAGMA ms")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in ("development", "dev", "local")

    @property
    def resolved_db_path(self) -> str:
        if os.path.isabs(self.DB_PATH):
            return self.DB_PATH
        return os.path.join(self.BASE_DIR, self.DB_PATH)

    @property
    def resolved_vector_path(self) -> str:
        if os.path.isabs(self.VECTOR_INDEX_PATH):
            return self.VECTOR_INDEX_PATH
        return os.path.join(self.BASE_DIR, self.VECTOR_INDEX_PATH)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Global singleton settings instance
settings = Settings()
