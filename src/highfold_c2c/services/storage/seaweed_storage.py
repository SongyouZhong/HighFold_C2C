"""
SeaweedFS Storage Implementation

Supports Filer API (primary) and S3 API (fallback).
"""

import logging
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

import aiohttp

from highfold_c2c.config import storage as storage_config

logger = logging.getLogger(__name__)


class SeaweedStorage:
    """SeaweedFS Filer API storage implementation."""

    def __init__(self):
        self.filer_endpoint = storage_config.filer_endpoint
        self.bucket = storage_config.bucket
        self.base_url = storage_config.get_filer_base_url()

        logger.info(
            "SeaweedStorage initialized: filer=%s, bucket=%s",
            self.filer_endpoint,
            self.bucket,
        )

    def _get_url(self, remote_key: str) -> str:
        """Build full Filer URL."""
        key = remote_key.lstrip("/")
        return f"{self.base_url}/{key}"

    # ── Upload ───────────────────────────────────────────────────────────

    async def upload_file(self, local_path: Path, remote_key: str) -> str:
        """Upload local file to SeaweedFS."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            with open(local_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename=Path(local_path).name)
                async with session.post(url, data=data) as response:
                    if response.status not in (200, 201):
                        text = await response.text()
                        raise Exception(
                            f"Upload failed: {response.status} - {text}"
                        )

        logger.info("Uploaded file: %s -> %s", local_path, remote_key)
        return remote_key

    async def upload_bytes(
        self, data: bytes, remote_key: str, content_type: Optional[str] = None
    ) -> str:
        """Upload bytes to SeaweedFS."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field(
                "file",
                data,
                filename=remote_key.split("/")[-1],
                content_type=content_type or "application/octet-stream",
            )
            async with session.post(url, data=form_data) as response:
                if response.status not in (200, 201):
                    text = await response.text()
                    raise Exception(
                        f"Upload failed: {response.status} - {text}"
                    )

        logger.info("Uploaded bytes: %d bytes -> %s", len(data), remote_key)
        return remote_key

    # ── Download ─────────────────────────────────────────────────────────

    async def download_file(self, remote_key: str, local_path: Path) -> Path:
        """Download file from SeaweedFS to local path."""
        url = self._get_url(remote_key)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    raise FileNotFoundError(f"File not found: {remote_key}")
                if response.status != 200:
                    text = await response.text()
                    raise Exception(
                        f"Download failed: {response.status} - {text}"
                    )
                with open(local_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

        logger.info("Downloaded file: %s -> %s", remote_key, local_path)
        return local_path

    async def download_bytes(self, remote_key: str) -> bytes:
        """Download file content as bytes."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    raise FileNotFoundError(f"File not found: {remote_key}")
                if response.status != 200:
                    text = await response.text()
                    raise Exception(
                        f"Download failed: {response.status} - {text}"
                    )
                data = await response.read()

        logger.debug("Downloaded bytes: %s (%d bytes)", remote_key, len(data))
        return data

    # ── URL / Metadata ───────────────────────────────────────────────────

    async def get_presigned_url(
        self, remote_key: str, expires: Optional[int] = None
    ) -> str:
        """Generate direct download URL (Filer doesn't require signing)."""
        url = self._get_url(remote_key)
        logger.debug("Generated download URL for %s", remote_key)
        return url

    async def get_file_info(self, remote_key: str) -> Dict:
        """Get metadata for a file (size, content_type, etag)."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            async with session.head(url) as response:
                if response.status == 404:
                    raise FileNotFoundError(f"File not found: {remote_key}")
                return {
                    "size": int(response.headers.get("Content-Length", 0)),
                    "content_type": response.headers.get("Content-Type", ""),
                    "etag": response.headers.get("ETag", ""),
                }

    async def file_exists(self, remote_key: str) -> bool:
        """Check if a file exists in storage."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            async with session.head(url) as response:
                return response.status == 200

    # ── Delete ───────────────────────────────────────────────────────────

    async def delete_file(self, remote_key: str) -> bool:
        """Delete file from SeaweedFS."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                if response.status not in (200, 202, 204, 404):
                    text = await response.text()
                    raise Exception(
                        f"Delete failed: {response.status} - {text}"
                    )

        logger.info("Deleted file: %s", remote_key)
        return True

    async def delete_files(self, remote_keys: List[str]) -> bool:
        """Batch delete files from SeaweedFS."""
        for key in remote_keys:
            await self.delete_file(key)
        return True

    # ── List ─────────────────────────────────────────────────────────────

    async def list_files(self, prefix: str) -> List[str]:
        """List files under a prefix in SeaweedFS Filer."""
        url = self._get_url(prefix)
        if not url.endswith("/"):
            url += "/"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers={"Accept": "application/json"}
            ) as response:
                if response.status == 404:
                    return []
                if response.status != 200:
                    text = await response.text()
                    raise Exception(
                        f"List failed: {response.status} - {text}"
                    )
                data = await response.json()

        entries = data.get("Entries", []) or []
        return [entry["FullPath"].split("/")[-1] for entry in entries]

    # ── Directory operations ─────────────────────────────────────────────

    async def upload_directory(
        self, local_dir: Path, remote_prefix: str
    ) -> List[str]:
        """Recursively upload a local directory to SeaweedFS."""
        local_dir = Path(local_dir)
        uploaded = []
        for local_file in local_dir.rglob("*"):
            if local_file.is_file():
                relative = local_file.relative_to(local_dir)
                remote_key = f"{remote_prefix.rstrip('/')}/{relative}"
                await self.upload_file(local_file, remote_key)
                uploaded.append(remote_key)
        return uploaded

    async def download_directory(
        self, remote_prefix: str, local_dir: Path
    ) -> List[Path]:
        """Download all files under a prefix to a local directory."""
        files = await self.list_files(remote_prefix)
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        for filename in files:
            remote_key = f"{remote_prefix.rstrip('/')}/{filename}"
            local_path = local_dir / filename
            await self.download_file(remote_key, local_path)
            downloaded.append(local_path)
        return downloaded

    # ── Stream ───────────────────────────────────────────────────────────

    async def get_file_stream(
        self, remote_key: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content as an async iterator of chunks."""
        url = self._get_url(remote_key)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    raise FileNotFoundError(f"File not found: {remote_key}")
                if response.status != 200:
                    text = await response.text()
                    raise Exception(
                        f"Stream failed: {response.status} - {text}"
                    )
                async for chunk in response.content.iter_chunked(chunk_size):
                    yield chunk

    # ── Bucket management ────────────────────────────────────────────────

    async def ensure_bucket_exists(self) -> None:
        """Ensure the bucket directory exists on the Filer."""
        url = f"{self.filer_endpoint}/buckets/{self.bucket}/"

        async with aiohttp.ClientSession() as session:
            async with session.head(url) as response:
                if response.status == 200:
                    return

            async with session.post(url) as response:
                if response.status not in (200, 201, 409):
                    text = await response.text()
                    logger.warning(
                        "Failed to create bucket directory: %s - %s",
                        response.status,
                        text,
                    )
