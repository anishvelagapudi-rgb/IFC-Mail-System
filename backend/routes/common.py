"""Small helpers shared by the route modules."""
import uuid
from datetime import datetime, timezone

from flask import abort, g, request


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Expected a JSON object.")
    return data


def text(v, limit: int = 500) -> str:
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        abort(400, "Expected text.")
    return str(v).strip()[:limit]


def text_list(v, limit: int = 20, each: int = 200) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        abort(400, "Expected a list.")
    return [t for t in (text(x, each) for x in v[:limit]) if t]


def uuid_or_none(v):
    if v in (None, ""):
        return None
    try:
        return str(uuid.UUID(str(v)))
    except ValueError:
        abort(400, "Bad id.")


def one(query, message: str = "Not found."):
    rows = query.limit(1).execute().data
    if not rows:
        abort(404, message)
    return rows[0]


def org_settings() -> dict:
    """The caller's org settings (RLS: any profile in the org may read)."""
    row = one(g.db.from_("organizations").select("settings").eq("id", g.user["orgId"]))
    return row["settings"] or {}


def mail_row(mail_id: str) -> dict:
    """A mail row the caller may see. Flask-side scoping first; RLS repeats it."""
    q = g.db.from_("mail_items").select("*").eq("id", uuid_or_none(mail_id)).eq("org_id", g.user["orgId"])
    if g.user["role"] != "admin":
        q = q.eq("member_id", g.user["memberId"]).neq("status", "needs_review")
    return one(q, "Mail item not found.")


def member_ids_in_org(ids) -> set[str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return set()
    rows = g.db.from_("members").select("id").eq("org_id", g.user["orgId"]).in_("id", ids).execute().data
    return {r["id"] for r in rows}
