"""Redis client and cache helpers for Supabase-backed reads. No-op when REDIS_URL is unset."""

import json
import os
from typing import Callable, TypeVar

from dotenv import load_dotenv

load_dotenv()

KEY_PREFIX = "legalens:"

# TTLs in seconds (invalidation also used on writes)
TTL_DOCUMENTS_LIST = 300   # 5 min
TTL_DOCUMENT_PATH = 300    # 5 min
TTL_ANALYSIS = 600         # 10 min
TTL_NEGOTIATED_CLAUSES = 600  # 10 min
TTL_SIGNED_URL_MAX = 3600  # 1 hour cap for signed URLs

_redis_client = None


def _get_redis():
    """Lazy Redis connection. Returns None if REDIS_URL is unset."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


def key_documents_list(user_id: str) -> str:
    return f"{KEY_PREFIX}documents:list:{user_id}"


def key_document_path(path: str, user_id: str) -> str:
    return f"{KEY_PREFIX}documents:path:{path}:{user_id}"


def key_analysis(document_id: str) -> str:
    return f"{KEY_PREFIX}document_analyses:{document_id}"


def key_negotiated_clauses(document_id: str) -> str:
    return f"{KEY_PREFIX}negotiated_clauses:{document_id}"


def key_signed_url(path: str) -> str:
    return f"{KEY_PREFIX}signed_url:{path}"


T = TypeVar("T")


def get_cached(key: str, fetcher: Callable[[], T], ttl: int) -> T:
    """
    Return value from Redis if present, else call fetcher(), store result, and return.
    If Redis is unavailable or key is missing, calls fetcher() and does not store.
    Value must be JSON-serializable (list, dict, str, None, numbers).
    """
    client = _get_redis()
    if client is None:
        return fetcher()
    try:
        raw = client.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        pass
    value = fetcher()
    try:
        client.setex(key, ttl, json.dumps(value))
    except Exception:
        pass
    return value


def _delete(key: str) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception:
        pass


def invalidate_documents_list(user_id: str) -> None:
    _delete(key_documents_list(user_id))


def invalidate_document_path(path: str, user_id: str) -> None:
    _delete(key_document_path(path, user_id))


def invalidate_analysis(document_id: str) -> None:
    _delete(key_analysis(document_id))


def invalidate_negotiated_clauses(document_id: str) -> None:
    _delete(key_negotiated_clauses(document_id))


def invalidate_signed_url(path: str) -> None:
    _delete(key_signed_url(path))
