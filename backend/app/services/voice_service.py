"""Speech synthesis through Deepgram Aura.

The browser's own speechSynthesis works and needs no key, but it sounds like
2010 and on a Mac will happily hand you a novelty voice. Aura is the upgrade.

The key stays on the server. Deepgram documents a temporary-key flow for
browser clients, but proxying costs one hop and means no credential of ours is
ever in a page - and the audio arriving as bytes we control is what lets the
client drive lip sync from the real waveform rather than approximating it.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SPEAK_URL = "https://api.deepgram.com/v1/speak"
# Plenty for one sentence; a whole reply is spoken in pieces as it streams.
MAX_CHARS = 1200
TIMEOUT = 20.0


class VoiceUnavailable(RuntimeError):
    """No Deepgram key configured, or the provider could not be reached."""


def is_enabled() -> bool:
    return bool(settings.deepgram_api_key)


def _client() -> httpx.AsyncClient:
    if not is_enabled():
        raise VoiceUnavailable(
            "Speech synthesis needs DEEPGRAM_API_KEY. Without it the client "
            "falls back to the browser's own voice."
        )
    return httpx.AsyncClient(timeout=TIMEOUT)


async def speak(text: str, *, model: str | None = None) -> tuple[bytes, str]:
    """Render one piece of text. Returns (audio, content type).

    MP3 by default: it is a fifth the size of raw PCM over the wire, and
    decodeAudioData handles it without us writing a WAV header.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise VoiceUnavailable("Nothing to say.")
    if len(cleaned) > MAX_CHARS:
        cleaned = cleaned[:MAX_CHARS]

    params: dict[str, Any] = {"model": model or settings.deepgram_tts_model}
    async with _client() as client:
        try:
            response = await client.post(
                SPEAK_URL,
                params=params,
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": cleaned},
            )
        except httpx.HTTPError as exc:
            logger.warning("Deepgram unreachable: %s", exc)
            raise VoiceUnavailable(f"Could not reach the speech service: {exc}") from exc

    if response.status_code != 200:
        # Deepgram puts the reason in the body; the status alone is not useful.
        detail = response.text[:200]
        logger.warning("Deepgram returned %s: %s", response.status_code, detail)
        if response.status_code in (401, 403):
            raise VoiceUnavailable("The speech service rejected the API key.")
        raise VoiceUnavailable(f"Speech synthesis failed ({response.status_code}).")

    return response.content, response.headers.get("content-type", "audio/mpeg")
