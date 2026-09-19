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


class SupabaseStorageBackend:
    """Supabase Storage over its REST API.

    The right pairing for a host without a persistent disk: files leave the
    process entirely, so a restart cannot lose them.
    """

    name = "supabase"

    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise StorageError(
                "STORAGE_PROVIDER=supabase requires SUPABASE_URL and SUPABASE_SERVICE_KEY"
            )
        self.base_url = settings.supabase_url.rstrip("/")
        self.bucket = settings.supabase_storage_bucket
        self.key = settings.supabase_service_key

    @property
    def public_prefix(self) -> str:
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/"

    def object_url(self, path: str) -> str:
        return f"{self.public_prefix}{path}"

    @staticmethod
    def object_path(filename: str) -> str:
        return f"{uuid.uuid4().hex}_{_safe_name(filename)}"

    async def save(self, data: bytes, filename: str, content_type: str) -> str:
        import httpx

        path = self.object_path(filename)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
                    content=data,
                    headers={
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": content_type,
                        "x-upsert": "false",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise StorageError(
                f"Supabase Storage rejected the upload ({exc.response.status_code}). "
                "Check that the bucket exists and is public."
            ) from exc
        except httpx.HTTPError as exc:
            raise StorageError(f"Supabase Storage is unreachable: {exc}") from exc
        return self.object_url(path)

    async def delete(self, url: str) -> None:
        import httpx

        if not url.startswith(self.public_prefix):
            raise StorageError("That URL does not belong to this Supabase bucket")
        path = url[len(self.public_prefix) :]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.delete(
                    f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
                    headers={"Authorization": f"Bearer {self.key}"},
                )
                # A missing object is already the state we want.
                if response.status_code not in (200, 204, 404):
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError(f"Could not delete from Supabase Storage: {exc}") from exc


_BACKENDS: dict[str, type] = {
    "local": LocalStorageBackend,
    "s3": S3StorageBackend,
    "supabase": SupabaseStorageBackend,
}

_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        factory = _BACKENDS.get(settings.storage_provider, LocalStorageBackend)
        _backend = factory()
        logger.info("Storage backend: %s", _backend.name)
    return _backend


def reset_storage() -> None:
    """Test helper: drop the cached backend so a settings change takes effect."""
    global _backend
    _backend = None
