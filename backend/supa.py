"""Supabase clients.

* user_db(token): PostgREST client that acts AS the caller (their JWT), so row-level security
  applies to every query. This is what API routes use for data.
* service(): service-role client. Bypasses RLS. Only for creating/deleting logins, Storage
  (after the route has done its own access check), public org list, and the seed script.
"""
from functools import lru_cache

from postgrest import SyncPostgrestClient
from supabase import Client, create_client

from . import config


def user_db(token: str) -> SyncPostgrestClient:
    return SyncPostgrestClient(
        f"{config.SUPABASE_URL}/rest/v1",
        headers={
            "apikey": config.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=20,
    )


@lru_cache(maxsize=1)
def service() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def anon() -> Client:
    """A fresh anon client per call: its auth helper keeps session state in memory."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)


# ---------------------------------------------------------------- storage helpers
def _bucket():
    return service().storage.from_(config.STORAGE_BUCKET)


def upload(path: str, data: bytes, content_type: str = "image/jpeg") -> None:
    _bucket().upload(path, data, {"content-type": content_type, "upsert": "true"})


def sign(paths: list[str]) -> dict[str, str]:
    """Short-lived signed URLs for private objects, keyed by path."""
    paths = [p for p in dict.fromkeys(paths) if p]
    if not paths:
        return {}
    out = {}
    for item in _bucket().create_signed_urls(paths, config.SIGNED_URL_TTL):
        if item.get("signedURL") and not item.get("error"):
            out[item["path"]] = item["signedURL"]
    return out


def remove(paths: list[str]) -> None:
    paths = [p for p in paths if p]
    if paths:
        _bucket().remove(paths)
