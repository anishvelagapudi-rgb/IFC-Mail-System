"""Sign-in, sign-up (pending until an admin approves), session refresh, password change."""
import logging

from flask import Blueprint, abort, g, jsonify
from werkzeug.exceptions import HTTPException

from .. import supa
from ..authz import MIN_PASSWORD, clean_username, require, username_to_email, validate_credentials
from .common import body, now, text, text_list, uuid_or_none

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


def _session_json(session) -> dict:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
    }


def _sign_in(username: str, password: str):
    try:
        res = supa.anon().auth.sign_in_with_password({"email": username_to_email(username), "password": password})
    except Exception:
        abort(401, "Wrong username or password.")
    if not res.session:
        abort(401, "Wrong username or password.")
    return res.session


@bp.get("/orgs")
def list_orgs():
    """Public: organizations a new member can register with (id + name only)."""
    rows = supa.service().table("organizations").select("id, name").order("name").execute().data
    return jsonify(rows)


@bp.post("/auth/login")
def login():
    b = body()
    username = clean_username(b.get("username"))
    password = b.get("password") or ""
    if not username or not password:
        abort(400, "Enter your username and password.")
    return jsonify(_session_json(_sign_in(username, password)))


@bp.post("/auth/refresh")
def refresh():
    token = (body().get("refresh_token") or "").strip()
    if not token:
        abort(401, "Please sign in.")
    try:
        res = supa.anon().auth.refresh_session(token)
    except Exception:
        abort(401, "Session expired. Please sign in again.")
    if not res.session:
        abort(401, "Session expired. Please sign in again.")
    return jsonify(_session_json(res.session))


def create_login(username: str, password: str, profile: dict) -> str:
    """Create a Supabase Auth user + profile row (service role). Returns the user id."""
    svc = supa.service()
    if svc.table("profiles").select("user_id").eq("username", username).limit(1).execute().data:
        abort(409, "That username is taken.")
    try:
        res = svc.auth.admin.create_user(
            {"email": username_to_email(username), "password": password, "email_confirm": True, "user_metadata": {"username": username}}
        )
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower():
            abort(409, "That username is taken.")
        log.warning("create_user failed: %s", msg)
        abort(400, "Could not create the account. Check the password and try again.")
    uid = res.user.id
    try:
        svc.table("profiles").insert({"user_id": uid, "username": username, **profile}).execute()
    except Exception:
        svc.auth.admin.delete_user(uid)
        raise
    return uid


@bp.post("/auth/register")
def register_member():
    """A person signs up with an existing org. They can sign in, but see nothing until approved."""
    b = body()
    username = clean_username(b.get("username"))
    password = b.get("password") or ""
    validate_credentials(username, password)
    org_id = uuid_or_none(b.get("orgId"))
    if not org_id or not supa.service().table("organizations").select("id").eq("id", org_id).limit(1).execute().data:
        abort(400, "Choose your organization.")
    p = b.get("profile") or {}
    name = text(p.get("name"), 120)
    if not name:
        abort(400, "Enter your full name.")
    registration = {
        "name": name,
        "aliases": text_list(p.get("aliases"), 10, 120),
        "phone": text(p.get("phone"), 40),
        "email": text(p.get("email"), 200),
        "submittedAt": now(),
    }
    create_login(username, password, {"org_id": org_id, "role": "member", "status": "pending", "display_name": name, "registration": registration})
    return jsonify(_session_json(_sign_in(username, password))), 201


@bp.get("/me")
@require("any")
def me():
    return jsonify(g.user)


@bp.post("/auth/password")
@require("any")
def change_password():
    b = body()
    new = b.get("newPassword") or ""
    if len(new) < MIN_PASSWORD:
        abort(400, f"Password must be at least {MIN_PASSWORD} characters.")
    try:
        _sign_in(g.user["username"], b.get("oldPassword") or "")  # proves the current password
    except HTTPException:
        abort(400, "Current password is wrong.")  # not 401: that would sign the user out
    supa.service().auth.admin.update_user_by_id(g.user["userId"], {"password": new})
    return jsonify({"ok": True})


@bp.post("/auth/logout")
@require("any")
def logout():
    try:
        supa.service().auth.admin.sign_out(g.token)  # revokes the refresh token
    except Exception:
        pass
    return jsonify({"ok": True})
