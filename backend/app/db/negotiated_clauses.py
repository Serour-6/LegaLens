"""Persist and retrieve negotiated clauses (output of the negotiate agent)."""

from app.cache.redis_cache import (
    TTL_NEGOTIATED_CLAUSES,
    get_cached,
    invalidate_negotiated_clauses,
    key_negotiated_clauses,
)
from app.db.client import supabase

TABLE = "negotiated_clauses"


def save_negotiated_clauses(document_id: str, clauses: list[dict]) -> list[dict]:
    """
    Save negotiation results for a document. Call after the negotiate agent runs.
    Each clause dict should have: id, type, severity, original_text, rewritten_clause,
    negotiation_script, priority, leverage, fallback_position.
    Uses upsert on (document_id, clause_id); replaces previous negotiations for this document.
    """
    if not clauses:
        return []

    rows = []
    for c in clauses:
        rows.append({
            "document_id": document_id,
            "clause_id": c.get("id", ""),
            "type": c.get("type"),
            "severity": c.get("severity"),
            "original_text": c.get("original_text"),
            "rewritten_clause": c.get("rewritten_clause"),
            "negotiation_script": c.get("negotiation_script"),
            "priority": c.get("priority"),
            "leverage": c.get("leverage"),
            "fallback_position": c.get("fallback_position"),
        })

    r = (
        supabase.table(TABLE)
        .upsert(rows, on_conflict="document_id,clause_id")
        .execute()
    )
    invalidate_negotiated_clauses(document_id)
    return r.data or []


def get_negotiated_clauses(document_id: str) -> list[dict]:
    """Return all negotiated clauses for a document, in insertion order."""
    r = (
        supabase.table(TABLE)
        .select("*")
        .eq("document_id", document_id)
        .order("created_at")
        .execute()
    )
    data = r.data or []
    # Normalize to the shape the frontend expects (id = clause_id for display)
    return [
        {
            "id": row.get("clause_id"),
            "type": row.get("type"),
            "severity": row.get("severity"),
            "original_text": row.get("original_text"),
            "rewritten_clause": row.get("rewritten_clause"),
            "negotiation_script": row.get("negotiation_script"),
            "priority": row.get("priority"),
            "leverage": row.get("leverage"),
            "fallback_position": row.get("fallback_position"),
        }
        for row in data
    ]


def get_negotiated_clauses_cached(document_id: str) -> list[dict]:
    """Return negotiated clauses for a document with Redis cache."""
    return get_cached(
        key_negotiated_clauses(document_id),
        lambda: get_negotiated_clauses(document_id),
        TTL_NEGOTIATED_CLAUSES,
    )
