"""Storage backends. The Supabase one is exercised against a fake transport."""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services.storage_service import (
    LocalStorageBackend,
    StorageError,
    SupabaseStorageBackend,
    get_storage,
    reset_storage,
)

SUPABASE_URL = "https://abcdefgh.supabase.co"


@pytest.fixture
def supabase(monkeypatch) -> SupabaseStorageBackend:
    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL + "/")
    monkeypatch.setattr(settings, "supabase_service_key", "service-role-key")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "resources")
    reset_storage()
    yield SupabaseStorageBackend()
    reset_storage()


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "http://x"), response=self
            )


class _FakeClient:
    """Records the request instead of making it."""

    calls: list[dict] = []
    response = _FakeResponse()

    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, content=None, headers=None):
        type(self).calls.append({"method": "POST", "url": url, "body": content, "headers": headers})
        return type(self).response

    async def delete(self, url, headers=None):
        type(self).calls.append({"method": "DELETE", "url": url, "headers": headers})
        return type(self).response


@pytest.fixture
def fake_http(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.response = _FakeResponse()
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return _FakeClient


# --- selection ------------------------------------------------------------- #
def test_provider_selection(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "local")
    reset_storage()
    assert isinstance(get_storage(), LocalStorageBackend)
    reset_storage()


def test_supabase_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    reset_storage()
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        get_storage()
    reset_storage()


# --- upload ---------------------------------------------------------------- #
async def test_upload_posts_to_the_bucket_and_returns_a_public_url(supabase, fake_http):
    url = await supabase.save(b"%PDF-1.4", "Lesson Plan #3.pdf", "application/pdf")

    call = fake_http.calls[0]
    assert call["method"] == "POST"
    assert call["url"].startswith(f"{SUPABASE_URL}/storage/v1/object/resources/")
    assert call["body"] == b"%PDF-1.4"
    assert call["headers"]["Authorization"] == "Bearer service-role-key"
    assert call["headers"]["Content-Type"] == "application/pdf"

    assert url.startswith(f"{SUPABASE_URL}/storage/v1/object/public/resources/")
    # Filename is sanitised but recognisable; the uuid prefix prevents collisions.
    assert url.endswith("_Lesson_Plan_3.pdf")


async def test_upload_failure_is_reported_clearly(supabase, fake_http):
    fake_http.response = _FakeResponse(status_code=404, text="Bucket not found")
    with pytest.raises(StorageError, match="bucket exists"):
        await supabase.save(b"x", "a.pdf", "application/pdf")


# --- delete ---------------------------------------------------------------- #
async def test_delete_targets_the_same_object(supabase, fake_http):
    url = supabase.object_url("abc123_notes.pdf")
    await supabase.delete(url)
    call = fake_http.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"] == f"{SUPABASE_URL}/storage/v1/object/resources/abc123_notes.pdf"


async def test_delete_rejects_foreign_urls(supabase, fake_http):
    with pytest.raises(StorageError, match="does not belong"):
        await supabase.delete("https://evil.example/storage/v1/object/public/resources/x.pdf")
    assert fake_http.calls == []


async def test_delete_tolerates_a_missing_object(supabase, fake_http):
    fake_http.response = _FakeResponse(status_code=404)
    await supabase.delete(supabase.object_url("gone.pdf"))  # must not raise


# --- local backend --------------------------------------------------------- #
async def test_local_backend_round_trip(tmp_path):
    backend = LocalStorageBackend(root=str(tmp_path), base_url="http://x/static/uploads")
    url = await backend.save(b"hello", "notes.txt", "text/plain")
    key = url.rsplit("/", 1)[-1]
    assert (tmp_path / "uploads" / key).read_bytes() == b"hello"

    await backend.delete(url)
    assert not (tmp_path / "uploads" / key).exists()


async def test_local_backend_cannot_escape_the_uploads_directory(tmp_path):
    """A crafted URL must never reach a file outside the uploads directory."""
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    backend = LocalStorageBackend(root=str(tmp_path / "store"), base_url="http://x/static/uploads")

    await backend.delete("http://x/static/uploads/../secret.txt")

    assert secret.exists(), "traversal must not delete files outside the store"
