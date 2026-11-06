"""Member requests (more time / scan / forward) and staff<->member messages."""
from flask import Blueprint, abort, g, jsonify, request

from .. import serialize
from ..authz import is_admin, require
from .common import body, mail_row, member_ids_in_org, now, one, text, text_list, uuid_or_none

bp = Blueprint("requests_messages", __name__)

REQUEST_TYPES = ("extra_time", "scan", "redirect")


# ---------------------------------------------------------------- requests
@bp.get("/requests")
@require("active")
def list_requests():
    q = g.db.from_("requests").select("*").eq("org_id", g.user["orgId"])
    if not is_admin():
        q = q.eq("member_id", g.user["memberId"])
    return jsonify([serialize.request_(r) for r in q.order("created_at", desc=True).execute().data])


def _payload(kind: str, p) -> dict:
    p = p if isinstance(p, dict) else {}
    if kind == "extra_time":
        try:
            days = int(p.get("days"))
        except (TypeError, ValueError):
            abort(400, "How many extra days?")
        if not 1 <= days <= 90:
            abort(400, "Extra time must be 1–90 days.")
        return {"days": days}
    if kind == "scan":
        return {}
    names = text_list(p.get("proxyNames"), 5, 120)
    if not names:
        abort(400, "Enter at least one name to forward to.")
    return {
        "proxyNames": names,
        "relationship": text(p.get("relationship"), 120),
        "phone": text(p.get("phone"), 40),
        "address": text(p.get("address"), 300),
        "contactId": uuid_or_none(p.get("contactId")),
    }


@bp.post("/requests")
@require("member")
def create_request():
    b = body()
    kind = b.get("type")
    if kind not in REQUEST_TYPES:
        abort(400, "Unknown request type.")
    mail = mail_row(b.get("mailId"))  # scoped to this member's visible mail
    if mail["status"] != "ready":
        abort(409, "This item is closed.")
    row = g.db.from_("requests").insert({
        "org_id": mail["org_id"],
        "mail_id": mail["id"],
        "member_id": g.user["memberId"],
        "type": kind,
        "status": "open",
        "payload": _payload(kind, b.get("payload")),
    }).execute().data[0]
    return jsonify(serialize.request_(row)), 201


@bp.post("/requests/<req_id>/resolve")
@require("admin")
def resolve(req_id):
    b = body()
    status = b.get("status")
    if status not in ("approved", "declined", "fulfilled"):
        abort(400, "Bad status.")
    r = one(g.db.from_("requests").select("*").eq("id", uuid_or_none(req_id)).eq("org_id", g.user["orgId"]), "Request not found.")
    r = g.db.from_("requests").update({"status": status, "resolved_at": now()}).eq("id", r["id"]).execute().data[0]
    note = text(b.get("note"), 1000)
    if note:
        g.db.from_("messages").insert({
            "org_id": r["org_id"], "member_id": r["member_id"], "mail_id": r["mail_id"], "request_id": r["id"],
            "sender": "system", "author_id": g.user["userId"], "body": note, "seen_by_staff": True,
        }).execute()
    return jsonify(serialize.request_(r))


# ---------------------------------------------------------------- messages
@bp.get("/messages")
@require("active")
def list_messages():
    q = g.db.from_("messages").select("*").eq("org_id", g.user["orgId"])
    if is_admin():
        if request.args.get("memberId"):
            q = q.eq("member_id", uuid_or_none(request.args["memberId"]))
    else:
        q = q.eq("member_id", g.user["memberId"])
    if request.args.get("mailId"):
        q = q.eq("mail_id", uuid_or_none(request.args["mailId"]))
    return jsonify([serialize.message(m) for m in q.order("created_at").execute().data])


@bp.post("/messages")
@require("active")
def send_message():
    b = body()
    msg = text(b.get("body"), 4000)
    if not msg:
        abort(400, "Write a message first.")
    mail_id = uuid_or_none(b.get("mailId"))
    if is_admin():
        member_id = uuid_or_none(b.get("memberId"))
        if not member_id or member_id not in member_ids_in_org([member_id]):
            abort(400, "Choose a member.")
        sender, seen = "staff", {"seen_by_staff": True}
    else:
        member_id = g.user["memberId"]
        sender, seen = "member", {"seen_by_member": True}
    if mail_id:
        mail = mail_row(mail_id)
        if mail["member_id"] != member_id:
            abort(400, "That mail item belongs to someone else.")
    row = g.db.from_("messages").insert({
        "org_id": g.user["orgId"], "member_id": member_id, "mail_id": mail_id,
        "request_id": uuid_or_none(b.get("requestId")), "sender": sender, "author_id": g.user["userId"],
        "body": msg, **seen,
    }).execute().data[0]
    return jsonify(serialize.message(row)), 201


@bp.post("/messages/seen")
@require("active")
def mark_seen():
    """Mark a member's thread read. Send mailId to mark only that item's thread; send
    mailId: null for the general thread; leave it out for everything."""
    b = body()
    if is_admin():
        member_id, field = uuid_or_none(b.get("memberId")), "seen_by_staff"
        if not member_id:
            abort(400, "Choose a member.")
    else:
        member_id, field = g.user["memberId"], "seen_by_member"
    q = g.db.from_("messages").update({field: True}).eq("org_id", g.user["orgId"]).eq("member_id", member_id).eq(field, False)
    if "mailId" in b:
        q = q.is_("mail_id", "null") if b["mailId"] is None else q.eq("mail_id", uuid_or_none(b["mailId"]))
    q.execute()
    return jsonify({"ok": True})
