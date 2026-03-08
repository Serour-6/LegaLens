"""Redis-backed cache for Supabase reads. Optional: if REDIS_URL is unset, cache is skipped."""

from app.cache.redis_cache import (
    get_cached,
    invalidate_analysis,
    invalidate_document_path,
    invalidate_documents_list,
    invalidate_negotiated_clauses,
    invalidate_signed_url,
    key_analysis,
    key_document_path,
    key_documents_list,
    key_negotiated_clauses,
    key_signed_url,
)

__all__ = [
    "get_cached",
    "invalidate_analysis",
    "invalidate_document_path",
    "invalidate_documents_list",
    "invalidate_negotiated_clauses",
    "invalidate_signed_url",
    "key_analysis",
    "key_document_path",
    "key_documents_list",
    "key_negotiated_clauses",
    "key_signed_url",
]
