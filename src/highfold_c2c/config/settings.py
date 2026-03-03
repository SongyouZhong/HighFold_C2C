"""
HighFold-C2C Settings

Central configuration settings loaded from environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

# Load .env file if available
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # Application
        self.APP_NAME: str = os.getenv("APP_NAME", "HighFold-C2C")
        self.APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

        # Database
        self.DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
        self.DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
        self.DB_USER: str = os.getenv("DB_USER", "admin")
        self.DB_PASSWORD: str = os.getenv("DB_PASSWORD", "secret")
        self.DB_NAME: str = os.getenv("DB_NAME", "mydatabase")

        # Task Processing
        self.TASK_QUERY_INTERVAL: int = int(os.getenv("TASK_QUERY_INTERVAL", "180"))
        self.MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "2"))

        # HighFold-specific
        self.C2C_CHECKPOINT_PATH: str = os.getenv(
            "C2C_CHECKPOINT_PATH", "checkpoints/c2c_model.pt"
        )
        self.COLABFOLD_BIN: str = os.getenv("COLABFOLD_BIN", "colabfold_batch")
        self.DEFAULT_MODEL_TYPE: str = os.getenv("DEFAULT_MODEL_TYPE", "alphafold2")
        self.DEFAULT_MSA_MODE: str = os.getenv("DEFAULT_MSA_MODE", "single_sequence")
        self.DEFAULT_NUM_MODELS: int = int(os.getenv("DEFAULT_NUM_MODELS", "5"))
        self.DEFAULT_SPAN_LEN: int = int(os.getenv("DEFAULT_SPAN_LEN", "5"))
        self.DEFAULT_NUM_SAMPLE: int = int(os.getenv("DEFAULT_NUM_SAMPLE", "20"))
        self.DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
        self.DEFAULT_TOP_P: float = float(os.getenv("DEFAULT_TOP_P", "0.9"))
        self.DEFAULT_SEED: int = int(os.getenv("DEFAULT_SEED", "42"))

        # Paths
        self.RESOURCE_DIR: str = os.getenv("RESOURCE_DIR", "/tmp/highfold_c2c/resource")
        self.TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/highfold_c2c")
        self.LOG_DIR: str = os.getenv("LOG_DIR", "/tmp/highfold_c2c/logs")

        # SeaweedFS Storage
        self.SEAWEEDFS_MASTER_URL: str = os.getenv(
            "SEAWEEDFS_MASTER_URL", "http://localhost:9333"
        )
        self.SEAWEEDFS_FILER_URL: str = os.getenv(
            "SEAWEEDFS_FILER_URL", "http://localhost:8888"
        )
        self.SEAWEEDFS_S3_URL: str = os.getenv(
            "SEAWEEDFS_S3_URL", "http://localhost:8333"
        )

    @property
    def database_url(self) -> str:
        """Get PostgreSQL database URL."""
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# ── Legacy Dictionary Configuration ──────────────────────────────────────────

DATABASE_CONFIG: Dict[str, Any] = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD", "secret"),
    "database": os.getenv("DB_NAME", "mydatabase"),
}

TASK_CONFIG: Dict[str, Any] = {
    "query_interval": int(os.getenv("TASK_QUERY_INTERVAL", "180")),
    "task_type": "highfold_c2c",
    "max_concurrent_tasks": int(os.getenv("MAX_CONCURRENT_TASKS", "2")),
}

PATHS: Dict[str, str] = {
    "resource_dir": os.getenv("RESOURCE_DIR", "/tmp/highfold_c2c/resource"),
    "temp_dir": os.getenv("TEMP_DIR", "/tmp/highfold_c2c"),
    "log_dir": os.getenv("LOG_DIR", "/tmp/highfold_c2c/logs"),
}
