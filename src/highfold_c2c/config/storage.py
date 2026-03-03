"""
SeaweedFS Storage Configuration
"""

import os
from pathlib import Path

api_type: str = os.getenv("SEAWEED_API_TYPE", "filer")
filer_endpoint: str = os.getenv("SEAWEED_FILER_ENDPOINT", "http://localhost:8888")
s3_endpoint: str = os.getenv("SEAWEED_S3_ENDPOINT", "http://localhost:8333")
access_key: str = os.getenv("SEAWEED_ACCESS_KEY", "")
secret_key: str = os.getenv("SEAWEED_SECRET_KEY", "")
bucket: str = os.getenv("SEAWEED_BUCKET", "astramolecula")
temp_dir: Path = Path(os.getenv("TEMP_DIR", "/tmp/highfold_c2c"))
presigned_url_expires: int = int(os.getenv("PRESIGNED_URL_EXPIRES", "3600"))


def get_filer_base_url() -> str:
    """Get the Filer bucket base URL."""
    return f"{filer_endpoint}/buckets/{bucket}"


def ensure_temp_dir() -> Path:
    """Ensure temporary directory exists and return it."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def get_storage_url(key: str) -> str:
    """Get the full storage URL for a given key."""
    base_url = get_filer_base_url()
    return f"{base_url}/{key.lstrip('/')}"
