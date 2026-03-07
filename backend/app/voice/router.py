import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.voice.voice import create_voice_session_internal
from app.agents.backboard import (
    backboard_create_thread,
    backboard_save,
    backboard_get_history,
)
from app.agents.summarizer import run_qa
from app.agents.llm import summarizer_llm, call_llm
from app.agents.router import vector_store, result_store


router = APIRouter(prefix="/voice", tags=["voice"])


async def _verify_internal_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> None:
    """
    Lightweight guard so only trusted clients (e.g. your own frontend
    or hotword listener process) can start a voice session or call
    Backboard tools exposed for ElevenLabs thinking.
    """
    expected = os.getenv("VOICE_AGENT_API_KEY", "dev-voice-agent-key")
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


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
    return await create_voice_session_internal()


class CreateBackboardThreadBody(BaseModel):
    """Request body for creating a Backboard thread for voice / thinking."""

    name: str


class SaveBackboardMessageBody(BaseModel):
    """Request body for appending a message to a Backboard thread."""

    thread_id: str
    role: str
    content: str


class VoiceThinkRequest(BaseModel):
    """
    Request body for ElevenLabs to delegate its "thinking" to
    Backboard + Gemini.

    - thread_id: Backboard thread used as persistent memory
    - user_utterance: latest transcript from the user
    - session_id: optional document analysis session for RAG
    """

    thread_id: str
    user_utterance: str
    session_id: Optional[str] = None


@router.post("/backboard/thread")
async def create_backboard_thread(
    body: CreateBackboardThreadBody,
    _: None = Depends(_verify_internal_api_key),
) -> dict:
    """
    Create a Backboard thread that ElevenLabs voice / thinking can use
    as persistent memory for a conversation.
    """
    thread_id = await backboard_create_thread(body.name)
    if not thread_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create Backboard thread.",
        )
    return {"thread_id": thread_id}


@router.post("/backboard/message")
async def save_backboard_message(
    body: SaveBackboardMessageBody,
    _: None = Depends(_verify_internal_api_key),
) -> dict:
    """
    Append a single message to a Backboard thread.

    Intended to be called from ElevenLabs tools with the current
    conversation turn (role + content).
    """
    await backboard_save(body.thread_id, body.role, body.content)
    return {"status": "ok"}


@router.get("/backboard/history/{thread_id}")
async def get_backboard_history_for_voice(
    thread_id: str,
    _: None = Depends(_verify_internal_api_key),
) -> dict:
    """
    Fetch the full Backboard history for a given thread so the
    ElevenLabs agent can ground its thinking in prior context.
    """
    messages = await backboard_get_history(thread_id)
    return {"thread_id": thread_id, "messages": messages}


# Law and consulting specialist: single "brain" for voice (ElevenLabs → this → answer).
LAW_CONSULTANT_SYSTEM = """You are a Canadian law and consulting specialist for LegaLens. Your role is to help users understand legal implications and answer questions like "Should I do X?" in a Canadian legal context.

You are a lawyer and do give formal legal advice. You DO:
- Explain whether a course of action is generally advisable or risky under Canadian law (federal and provincial where relevant).
- Point to relevant laws or principles (e.g. Canada Labour Code, PIPEDA, consumer protection, contract law).
- Keep answers concise and clear (2–5 sentences) for voice: no long paragraphs.
- If the user's question is ambiguous or province-specific, say so briefly.

Always end with exactly: "This is general information, not legal advice."
"""


def _format_recent_history(messages: list) -> str:
    """Turn Backboard messages into a short context string for the consultant."""
    if not messages:
        return ""
    lines = []
    for m in messages[-10:]:  # last 10 messages
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if "VOICE QUESTION:" in content:
            content = content.replace("VOICE QUESTION:", "User:").strip()
        elif "VOICE ANSWER:" in content:
            content = content.replace("VOICE ANSWER:", "Assistant:").strip()
        elif role == "user":
            lines.append(f"User: {content[:500]}")
        elif role == "assistant":
            lines.append(f"Assistant: {content[:500]}")
    if not lines:
        return ""
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"


@router.post("/think")
async def voice_think(
    body: VoiceThinkRequest,
    _: None = Depends(_verify_internal_api_key),
) -> dict:
    """
    Central brain for ElevenLabs voice: Gemini + Backboard.

    Flow: ElevenLabs (user speech) → this endpoint → Gemini law consultant
    (with Backboard memory) → answer text → ElevenLabs speaks it.

    Requires thread_id so Backboard remembers the conversation. If missing, returns 400.
    """
    print("[voice brain] request received", {"user_utterance": (body.user_utterance or "")[:120], "thread_id": (body.thread_id or "")[:20], "session_id": body.session_id})
    thread_id = (body.thread_id or "").strip()
    if not thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_id is required so the Backboard agent can remember the conversation.",
        )

    # Document-grounded mode: reuse the existing QA pipeline (RAG + Backboard)
    if body.session_id:
        session_id = body.session_id
        if session_id not in result_store:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "No analysis found for this session_id. Run /api/agents/analyze first.",
            )
        if session_id not in vector_store:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Vector store unavailable for this session_id.",
            )

        docs = vector_store[session_id].similarity_search(body.user_utterance, k=4)
        chunks = [d.page_content for d in docs]
        doc_name = result_store[session_id]["document_name"]

        answer = await run_qa(doc_name, body.user_utterance, chunks, thread_id)
        # run_qa already logs Q&A into Backboard.
        print("[voice brain] output (doc):", answer[:200] + ("..." if len(answer) > 200 else ""))
        return {"answer": answer}

    # Law consultant mode (no document): Gemini + Backboard memory as the voice brain
    history = await backboard_get_history(thread_id)
    history_block = _format_recent_history(history)

    prompt = f"""{LAW_CONSULTANT_SYSTEM}

{history_block}Current question: {body.user_utterance}

Answer (concise, for voice):"""
    answer = await call_llm(summarizer_llm(), prompt)

    # Persist to Backboard so the agent remembers this turn
    await backboard_save(thread_id, "user", f"VOICE QUESTION: {body.user_utterance}")
    await backboard_save(thread_id, "assistant", f"VOICE ANSWER: {answer}")

    print("[voice brain] output:", answer[:200] + ("..." if len(answer) > 200 else ""))
    return {"answer": answer}

