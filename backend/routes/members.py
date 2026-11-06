"""Members (the mail roster), trusted contacts, logins and account approval."""
from flask import Blueprint, abort, g, jsonify

from .. import serialize
from ..authz import clean_username, is_admin, require, validate_credentials
from .auth import create_login
from .common import body, now, one, text, text_list, uuid_or_none

bp = Blueprint("members", __name__)


def _members_json(rows: list[dict]) -> list[dict]:
    ids = [m["id"] for m in rows]
    contacts, accounts = {}, {}
    if ids:
        for c in g.db.from_("trusted_contacts").select("*").in_("member_id", ids).order("created_at").execute().data:
            contacts.setdefault(c["member_id"], []).append(c)
        if is_admin():
            for p in g.db.from_("profiles").select("user_id, member_id").eq("org_id", g.user["orgId"]).in_("member_id", ids).execute().data:
                accounts[p["member_id"]] = p
    return [serialize.member(m, contacts.get(m["id"], []), accounts.get(m["id"])) for m in rows]


def _member_row(member_id: str) -> dict:
    member_id = uuid_or_none(member_id)
    if not is_admin() and member_id != g.user["memberId"]:
        abort(404, "Member not found.")
    return one(g.db.from_("members").select("*").eq("id", member_id).eq("org_id", g.user["orgId"]), "Member not found.")


@bp.get("/members")
@require("admin")
def list_members():
    rows = g.db.from_("members").select("*").eq("org_id", g.user["orgId"]).order("name").execute().data
    return jsonify(_members_json(rows))


@bp.get("/members/<member_id>")
@require("active")
def get_member(member_id):
    return jsonify(_members_json([_member_row(member_id)])[0])


def _fields(b: dict) -> dict:
    out = {}
    if "name" in b:
        out["name"] = text(b["name"], 120)
        if not out["name"]:
            abort(400, "Enter a name.")
    if "aliases" in b:
        out["aliases"] = text_list(b["aliases"], 10, 120)
    if "phone" in b:
        out["phone"] = text(b["phone"], 40)
    if "email" in b:
        out["email"] = text(b["email"], 200)
    return out


def _sync_contacts(member: dict, contacts) -> None:
    """Make the member's trusted contacts match the list sent by the app.

    Ids the browser generated for new contacts are kept (the forward-request flow refers to
    them), as long as they are valid UUIDs; PK collisions simply fail."""
    if not isinstance(contacts, list) or len(contacts) > 20:
        abort(400, "Bad trusted contacts list.")
    existing = {c["id"]: c for c in g.db.from_("trusted_contacts").select("*").eq("member_id", member["id"]).execute().data}
    keep = set()
    for c in contacts:
        if not isinstance(c, dict):
            abort(400, "Bad trusted contact.")
        cid = uuid_or_none(c.get("id"))
        row = {k: text(c.get(k), 300) for k in ("name", "relationship", "phone", "address")}
        if not row["name"]:
            abort(400, "Each trusted person needs a name.")
        if cid in existing:
            keep.add(cid)
            if any(existing[cid].get(k) != v for k, v in row.items()):
                g.db.from_("trusted_contacts").update(row).eq("id", cid).execute()
        else:
            ins = {**row, "member_id": member["id"], "org_id": member["org_id"]}
            if cid:
                ins["id"] = cid
            new = g.db.from_("trusted_contacts").insert(ins).execute().data
            keep.add(new[0]["id"])
    gone = [cid for cid in existing if cid not in keep]
    if gone:
        g.db.from_("trusted_contacts").delete().in_("id", gone).execute()


@bp.post("/members")
@require("admin")
def create_member():
    b = body()
    f = _fields({"name": b.get("name"), **{k: b[k] for k in ("aliases", "phone", "email") if k in b}})
    row = g.db.from_("members").insert({**f, "org_id": g.user["orgId"]}).execute().data[0]
    if "trustedContacts" in b:
        _sync_contacts(row, b["trustedContacts"])
    return jsonify(_members_json([row])[0]), 201


@bp.patch("/members/<member_id>")
@require("active")
def update_member(member_id):
    """Admins edit anyone in their org; a member edits only their own details and contacts."""
    m = _member_row(member_id)
    b = body()
    f = _fields(b)
    if f:
        m = g.db.from_("members").update(f).eq("id", m["id"]).execute().data[0]
    if "trustedContacts" in b:
        _sync_contacts(m, b["trustedContacts"])
    return jsonify(_members_json([m])[0])


# ---------------------------------------------------------------- logins
@bp.get("/accounts")
@require("admin")
def list_accounts():
    rows = g.db.from_("profiles").select("*").eq("org_id", g.user["orgId"]).order("created_at").execute().data
    return jsonify([serialize.account(p) for p in rows])


@bp.post("/staff")
@require("admin")
def create_staff():
    b = body()
    username = clean_username(b.get("username"))
    password = b.get("password") or ""
    validate_credentials(username, password)
    uid = create_login(
        username,
        password,
        {"org_id": g.user["orgId"], "role": "admin", "status": "active", "display_name": text(b.get("name"), 120),
         "approved_by": g.user["userId"], "approved_at": now()},
    )
    p = one(g.db.from_("profiles").select("*").eq("user_id", uid))
    return jsonify(serialize.account(p)), 201


def _pending(user_id: str) -> dict:
    p = one(
        g.db.from_("profiles").select("*").eq("user_id", uuid_or_none(user_id)).eq("org_id", g.user["orgId"]).eq("role", "member"),
        "Account not found.",
    )
    if p["status"] == "active":
        abort(409, "This account is already approved.")
    return p


@bp.post("/accounts/<user_id>/approve")
@require("admin")
def approve(user_id):
    """Approve a member sign-up: link it to an existing roster entry, or create a new one from
    what they entered. Only then can they see mail."""
    p = _pending(user_id)
    reg = p.get("registration") or {}
    member_id = uuid_or_none(body().get("memberId"))
    if member_id:
        m = one(g.db.from_("members").select("*").eq("id", member_id).eq("org_id", g.user["orgId"]), "Member not found.")
        if g.db.from_("profiles").select("user_id").eq("member_id", member_id).limit(1).execute().data:
            abort(409, "That member already has a login.")
        # Fill gaps from the sign-up, and remember the name they used as an alias.
        upd = {"registered_at": now()}
        if not m.get("phone") and reg.get("phone"):
            upd["phone"] = reg["phone"]
        if not m.get("email") and reg.get("email"):
            upd["email"] = reg["email"]
        aliases = list(m.get("aliases") or [])
        for a in [reg.get("name"), *(reg.get("aliases") or [])]:
            if a and a != m["name"] and a not in aliases:
                aliases.append(a)
        upd["aliases"] = aliases[:10]
        g.db.from_("members").update(upd).eq("id", member_id).execute()
    else:
        m = g.db.from_("members").insert({
            "org_id": g.user["orgId"],
            "name": reg.get("name") or p["display_name"] or p["username"],
            "aliases": reg.get("aliases") or [],
            "phone": reg.get("phone") or "",
            "email": reg.get("email") or "",
            "registered_at": now(),
        }).execute().data[0]
        member_id = m["id"]
    g.db.from_("profiles").update(
        {"status": "active", "member_id": member_id, "approved_by": g.user["userId"], "approved_at": now()}
    ).eq("user_id", p["user_id"]).execute()
    return jsonify({"ok": True, "memberId": member_id})


@bp.post("/accounts/<user_id>/reject")
@require("admin")
def reject(user_id):
    p = _pending(user_id)
    g.db.from_("profiles").update({"status": "rejected", "approved_by": g.user["userId"], "approved_at": now()}).eq("user_id", p["user_id"]).execute()
    return jsonify({"ok": True})
