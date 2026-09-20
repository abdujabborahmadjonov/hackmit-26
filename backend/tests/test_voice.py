"""Hosted speech synthesis.

CI has no Deepgram key, so these cover the contract around it: the disabled
path, authorisation, validation, and that the key never leaves the server.
The one test that would call Deepgram is skipped unless a key is present.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import voice_service
from tests.conftest import register, requires_db

pytestmark = [requires_db, pytest.mark.integration]

SPEAK = "/voice/speak"
BODY = {"text": "Silence at two hundred is a seating problem.", "mentor": "osmar-zaiane"}


async def test_status_reports_the_browser_fallback_without_a_key(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "")
    body = (await client.get("/voice/status")).json()
    assert body == {"enabled": False, "provider": "browser", "model": None}


async def test_status_names_the_provider_and_voice_once_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    body = (await client.get("/voice/status")).json()
    assert body["enabled"] is True
    assert body["provider"] == "deepgram"
    assert body["model"] == settings.deepgram_tts_model


async def test_speak_is_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "")
    account = await register(client)
    response = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


async def test_speak_requires_authentication(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    assert (await client.post(SPEAK, json=BODY)).status_code == 401


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "x" * (voice_service.MAX_CHARS + 1)}, {}],
    ids=["empty", "too-long", "missing"],
)
async def test_speak_validates_its_input(client, monkeypatch, body):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    account = await register(client)
    assert (await client.post(SPEAK, json=body, headers=account["headers"])).status_code == 422


async def test_speak_404s_on_an_unknown_mentor(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    account = await register(client)
    response = await client.post(
        SPEAK, json={"text": "hello", "mentor": "nobody"}, headers=account["headers"]
    )
    assert response.status_code == 404


async def test_the_key_never_reaches_the_client(client, monkeypatch):
    """The whole reason this is a proxy rather than a temporary browser key."""
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-value")
    body = (await client.get("/voice/status")).json()
    assert "dg-secret-value" not in str(body)

    account = await register(client)
    response = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert "dg-secret-value" not in response.text


async def test_a_provider_failure_becomes_a_503_not_a_500(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")

    async def boom(text, *, model=None):
        raise voice_service.VoiceUnavailable("The speech service rejected the API key.")

    monkeypatch.setattr(voice_service, "speak", boom)
    account = await register(client)
    response = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert response.status_code == 503
    assert "rejected" in response.json()["detail"]


async def test_audio_comes_back_as_audio(client, monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")

    async def fake(text, *, model=None):
        return b"ID3fake-mp3-bytes", "audio/mpeg"

    monkeypatch.setattr(voice_service, "speak", fake)
    account = await register(client)
    response = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3fake-mp3-bytes"


@pytest.mark.skipif(not settings.deepgram_api_key, reason="No DEEPGRAM_API_KEY configured")
async def test_deepgram_actually_returns_audio(client):
    account = await register(client)
    response = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) > 1000


@pytest.mark.skipif(not settings.deepgram_api_key, reason="No DEEPGRAM_API_KEY configured")
async def test_the_pooled_client_survives_a_new_event_loop(client):
    """The pool belongs to the loop that opened it. Caching it by nothing but
    "is it closed" reuses a dead loop's connections on the next one."""
    account = await register(client)
    first = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert first.status_code == 200
    # Same process, second call - in the suite this is a different loop than
    # the one that built the client for an earlier test.
    second = await client.post(SPEAK, json=BODY, headers=account["headers"])
    assert second.status_code == 200
