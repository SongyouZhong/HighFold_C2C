"""
PostgreSQL Database Configuration
"""

import os
from pathlib import Path
from typing import Any, Dict

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class DatabaseConfig:
    """Database configuration class."""

    host: str = os.getenv("DB_HOST", "127.0.0.1")
    port: int = int(os.getenv("DB_PORT", "5432"))
    user: str = os.getenv("DB_USER", "admin")
    password: str = os.getenv("DB_PASSWORD", "secret")
    database: str = os.getenv("DB_NAME", "mydatabase")
    pool_min_size: int = int(os.getenv("DB_POOL_MIN", "1"))
    pool_max_size: int = int(os.getenv("DB_POOL_MAX", "10"))

    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        self.host = host or DatabaseConfig.host
        self.port = port or DatabaseConfig.port
        self.user = user or DatabaseConfig.user
        self.password = password or DatabaseConfig.password
        self.database = database or DatabaseConfig.database

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
        }


DB_CONFIG: Dict[str, Any] = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD", "secret"),
    "database": os.getenv("DB_NAME", "mydatabase"),
}

POOL_CONFIG: Dict[str, int] = {
    "min_size": int(os.getenv("DB_POOL_MIN", "1")),
    "max_size": int(os.getenv("DB_POOL_MAX", "10")),
}
