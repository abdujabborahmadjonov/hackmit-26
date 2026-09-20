"""Speech synthesis for mentor chat.

A thin proxy in front of Deepgram so the key stays server side. The client
posts one sentence at a time as the reply streams, which is what lets the
mentor start talking before the answer has finished generating.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.config import settings
from app.services import mentor_service, voice_service
from app.services.voice_service import VoiceUnavailable
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

# One request per spoken sentence, so a single reply is several calls.
speak_rate_limit = RateLimiter("voice_speak", settings.tts_rate_limit_per_minute)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=voice_service.MAX_CHARS)
    mentor: str | None = Field(
        default=None, description="Use this mentor's configured voice"
    )


class VoiceStatus(BaseModel):
    enabled: bool
    provider: str
    model: str | None


@router.get("/status", response_model=VoiceStatus, summary="Is hosted speech configured?")
async def voice_status() -> VoiceStatus:
    """Lets the client choose a provider before it needs to speak."""
    if voice_service.is_enabled():
        return VoiceStatus(enabled=True, provider="deepgram", model=settings.deepgram_tts_model)
    # The browser can still speak for itself; it just sounds worse.
    return VoiceStatus(enabled=False, provider="browser", model=None)


@router.post(
    "/speak",
    dependencies=[Depends(speak_rate_limit)],
    summary="Render one piece of speech",
    description=(
        "Returns audio for a sentence of a mentor's reply. Posted per sentence "
        "rather than per reply so the mentor can start talking while the rest "
        "is still being generated. Returns 503 when no speech key is "
        "configured - the client then falls back to the browser's own voice."
    ),
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def speak(body: SpeakRequest, current_user: CurrentUser) -> Response:
    if not voice_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted speech is not configured on this deployment.",
        )

    model: str | None = None
    if body.mentor:
        mentor = mentor_service.get_mentor(body.mentor)
        if mentor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such mentor")
        model = mentor.voice.model or None

    try:
        audio, content_type = await voice_service.speak(body.text, model=model)
    except VoiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return Response(
        content=audio,
        media_type=content_type,
        # The same sentence is never requested twice in a conversation, but a
        # reload of the same reply would be.
        headers={"Cache-Control": "private, max-age=3600"},
    )

