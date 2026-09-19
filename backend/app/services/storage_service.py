"""File storage abstraction: local disk (default) or any S3-compatible bucket."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class StorageBackend(Protocol):
    name: str

    async def save(self, data: bytes, filename: str, content_type: str) -> str:
        """Persist the bytes and return a publicly reachable URL."""

    async def delete(self, url: str) -> None:
        ...


def _safe_name(filename: str) -> str:
    base = os.path.basename(filename or "file")
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ").strip().replace(" ", "_")
    return cleaned[-120:] or "file"


class LocalStorageBackend:
    """Writes into STORAGE_LOCAL_DIR/uploads, served by the app at /static/uploads."""

    name = "local"

    def __init__(self, root: str | None = None, base_url: str | None = None) -> None:
        self.root = Path(root or settings.storage_local_dir).resolve() / "uploads"
        self.base_url = (base_url or settings.storage_public_base_url).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, data: bytes, filename: str, content_type: str) -> str:
        key = f"{uuid.uuid4().hex}_{_safe_name(filename)}"
        path = self.root / key
        path.write_bytes(data)
        return f"{self.base_url}/{key}"

    async def delete(self, url: str) -> None:
        key = url.rsplit("/", 1)[-1]
        path = (self.root / key).resolve()
        # Never let a crafted URL escape the uploads directory.
        if path.parent != self.root:
            raise StorageError("Refusing to delete a file outside the uploads directory")
        if path.exists():
            path.unlink()


class S3StorageBackend:
    """Any S3-compatible store (AWS S3, MinIO, R2). Requires boto3."""

    name = "s3"

    def __init__(self) -> None:
        try:
            import boto3  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise StorageError(
                "STORAGE_PROVIDER=s3 requires boto3 (pip install boto3)"
            ) from exc
        if not settings.s3_bucket:
            raise StorageError("STORAGE_PROVIDER=s3 requires S3_BUCKET")
        self.bucket = settings.s3_bucket

    def _client(self):  # pragma: no cover - needs real credentials
        import boto3

        return boto3.client(
            "s3",
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )

    async def save(self, data: bytes, filename: str, content_type: str) -> str:  # pragma: no cover
        import asyncio

        key = f"resources/{uuid.uuid4().hex}_{_safe_name(filename)}"

        def _put() -> None:
            self._client().put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )

        await asyncio.to_thread(_put)
        if settings.storage_public_base_url:
            return f"{settings.storage_public_base_url.rstrip('/')}/{key}"
        if settings.s3_endpoint_url:  # MinIO / R2 / any custom endpoint
            return f"{settings.s3_endpoint_url.rstrip('/')}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"

    async def delete(self, url: str) -> None:  # pragma: no cover
        import asyncio

        key = url.split("/resources/", 1)[-1]

        def _delete() -> None:
            self._client().delete_object(Bucket=self.bucket, Key=f"resources/{key}")

        await asyncio.to_thread(_delete)


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = S3StorageBackend() if settings.storage_provider == "s3" else LocalStorageBackend()
        logger.info("Storage backend: %s", _backend.name)
    return _backend
