import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from elevenlabs.client import AsyncElevenLabs  # type: ignore[import-not-found]

router = APIRouter(prefix="/voice", tags=["voice"])


def _get_required_env(name: str) -> str:
    """Return a required environment variable or raise a 500 error."""
    value = os.getenv(name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is not configured on the server.",
        )
    return value


async def _verify_internal_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> None:
    """
    Lightweight guard so only trusted clients (e.g. your own frontend
    or hotword listener process) can start a voice session.
    """
    expected = os.getenv("VOICE_AGENT_API_KEY", "dev-voice-agent-key")
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def _get_elevenlabs_client() -> AsyncElevenLabs:
    """
    Construct an AsyncElevenLabs client using the server-side API key.
    Keeping this on the backend avoids exposing the key to the browser.
    """
    api_key = _get_required_env("ELEVENLABS_API_KEY")
    return AsyncElevenLabs(api_key=api_key)


@router.post("/session")
async def create_voice_session(
    _: None = Depends(_verify_internal_api_key),
) -> dict:
    """
    Create a short-lived ElevenLabs conversational session and return
    connection details for the caller.

    Typical flow:
    - a hotword listener detects "Hey Assistant"
    - it calls this endpoint
    - the frontend then uses the returned data with the ElevenLabs
      Conversational AI SDK to open a WebRTC / WebSocket connection
      and run the actual audio conversation loop.
    """
    agent_id = _get_required_env("AGENT_ID")
    client = _get_elevenlabs_client()

    # For private agents, ElevenLabs requires a WebRTC token.
    token_response = await client.conversational_ai.conversations.get_webrtc_token(
        agent_id=agent_id,
    )

    token: Optional[str] = getattr(token_response, "token", None)
    if token is None and isinstance(token_response, dict):
        token = token_response.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to obtain a WebRTC token from ElevenLabs.",
        )

    # The frontend or native client is responsible for using this token
    # with the ElevenLabs Conversational AI SDK to start the audio session.
    return {
        "agent_id": agent_id,
        "webrtc_token": token,
        "connection_type": "webrtc",
    }

