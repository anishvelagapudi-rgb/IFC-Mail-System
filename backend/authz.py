"""Authentication (Supabase JWT) and role checks for every API route.

Each request carries `Authorization: Bearer <access token>`. We verify the token, load the
caller's profile, and put it on `g.user`. Routes then declare who may call them:

    @require("admin")      active admin of an org
    @require("member")     active member with a linked roster entry
    @require("active")     either of the above
    @require("any")        any logged-in user, including one still pending approval

Routes must ALSO scope every query to g.user's org (admins) or member (members). RLS in the
database repeats those rules as a second layer.
"""
import re
from functools import wraps

import jwt
from flask import abort, g, request

from . import config, supa

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
MIN_PASSWORD = 8

_jwks = None


def _decode(token: str) -> dict:
    global _jwks
    opts = {"require": ["exp", "sub"]}
    if config.SUPABASE_JWT_SECRET:
        return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated", options=opts)
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)
    key = _jwks.get_signing_key_from_jwt(token)
    return jwt.decode(token, key, algorithms=["ES256", "RS256", "EdDSA"], audience="authenticated", options=opts)


def username_to_email(username: str) -> str:
    return f"{username}@{config.AUTH_EMAIL_DOMAIN}"


def clean_username(u) -> str:
    return (u or "").strip().lower()


def validate_credentials(username: str, password: str) -> None:
    if not USERNAME_RE.match(username):
        abort(400, "Username: 3–32 characters, letters, numbers, . _ or -")
    if len(password or "") < MIN_PASSWORD:
        abort(400, f"Password must be at least {MIN_PASSWORD} characters.")


def _load_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        abort(401, "Please sign in.")
    token = header[7:].strip()
    try:
        claims = _decode(token)
    except jwt.ExpiredSignatureError:
        abort(401, "Session expired.")
    except Exception:
        abort(401, "Please sign in.")

    g.db = supa.user_db(token)
    g.token = token
    rows = (
        g.db.from_("profiles")
        .select("user_id, org_id, role, status, username, display_name, member_id, organizations(name)")
        .eq("user_id", claims["sub"])
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        abort(403, "This login has no profile. Ask staff for help.")
    p = rows[0]
    g.user = {
        "userId": p["user_id"],
        "orgId": p["org_id"],
        "role": p["role"],
        "status": p["status"],
        "memberId": p["member_id"],
        "username": p["username"],
        "name": p["display_name"],
        "orgName": (p.get("organizations") or {}).get("name", ""),
    }


def require(level: str):
    assert level in ("admin", "member", "active", "any")

    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            _load_user()
            u = g.user
            if level != "any":
                if u["status"] != "active":
                    abort(403, "Your account is waiting for staff approval.")
                if level == "admin" and u["role"] != "admin":
                    abort(403, "Staff only.")
                if level == "member" and (u["role"] != "member" or not u["memberId"]):
                    abort(403, "Members only.")
                if u["role"] == "member" and not u["memberId"]:
                    abort(403, "Your account is not linked yet.")
            return fn(*a, **kw)

        return wrapper

    return deco


def is_admin() -> bool:
    return g.user["role"] == "admin"
