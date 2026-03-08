import uuid

from app.cache.redis_cache import (
    TTL_DOCUMENTS_LIST,
    TTL_DOCUMENT_PATH,
    TTL_SIGNED_URL_MAX,
    get_cached,
    invalidate_document_path,
    invalidate_documents_list,
    invalidate_signed_url,
    key_document_path,
    key_documents_list,
    key_signed_url,
)
from app.db.client import supabase

BUCKET_NAME = "legal documents"


def _safe_user_id(user_id: str) -> str:
    """Replace characters invalid in storage paths."""
    return user_id.replace("|", "_")

def ensure_bucket_exists() -> None:
    """Create the storage bucket if it doesn't already exist."""
    existing = [b.name for b in supabase.storage.list_buckets()]
    if BUCKET_NAME not in existing:
        supabase.storage.create_bucket(BUCKET_NAME, options={"public": False})


def upload_pdf(file_bytes: bytes, original_filename: str, user_id: str) -> dict:
    """Upload a PDF to the documents bucket scoped to the user."""
    safe_id = _safe_user_id(user_id)
    file_id = uuid.uuid4().hex
    storage_path = f"{safe_id}/{file_id}/{original_filename}"

    ensure_bucket_exists()

    supabase.storage.from_(BUCKET_NAME).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": "application/pdf"},
    )

    # Record metadata in the documents table
    supabase.table("documents").insert({
        "user_id": user_id,
        "bucket_path": storage_path,
        "filename": original_filename,
        "size_bytes": len(file_bytes),
    }).execute()

    invalidate_documents_list(user_id)
    return {"bucket": BUCKET_NAME, "path": storage_path}


def list_files(user_id: str) -> list[dict]:
    """List all documents belonging to a specific user from the database."""
    result = (
        supabase.table("documents")
        .select("id, filename, bucket_path, size_bytes, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def list_files_cached(user_id: str) -> list[dict]:
    """List all documents for a user, with Redis cache."""
    return get_cached(
        key_documents_list(user_id),
        lambda: list_files(user_id),
        TTL_DOCUMENTS_LIST,
    )


def get_document_by_path(path: str, user_id: str) -> dict | None:
    """Return document row if path exists and belongs to user."""
    result = (
        supabase.table("documents")
        .select("id, filename, bucket_path, size_bytes, created_at")
        .eq("bucket_path", path)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def get_document_by_path_cached(path: str, user_id: str) -> dict | None:
    """Return document row by path and user, with Redis cache."""
    return get_cached(
        key_document_path(path, user_id),
        lambda: get_document_by_path(path, user_id),
        TTL_DOCUMENT_PATH,
    )


def download_file(path: str) -> bytes:
    """Download file bytes from storage. Caller must verify ownership first."""
    data = supabase.storage.from_(BUCKET_NAME).download(path)
    return data


def get_signed_url(path: str, expires_in: int = 3600) -> str:
    """Generate a temporary signed URL for a stored file."""
    res = supabase.storage.from_(BUCKET_NAME).create_signed_url(path, expires_in)
    return res["signedURL"]


def get_signed_url_cached(path: str, expires_in: int = 3600) -> str:
    """Generate a signed URL with Redis cache. TTL is min(expires_in, 1 hour)."""
    ttl = min(expires_in, TTL_SIGNED_URL_MAX)
    return get_cached(
        key_signed_url(path),
        lambda: get_signed_url(path, expires_in),
        ttl,
    )


def delete_file(path: str, user_id: str) -> None:
    """Delete a file from the bucket and its database record. user_id used for cache invalidation."""
    supabase.storage.from_(BUCKET_NAME).remove([path])
    supabase.table("documents").delete().eq("bucket_path", path).execute()
    invalidate_documents_list(user_id)
    invalidate_document_path(path, user_id)
    invalidate_signed_url(path)
