"""Per-org settings, the follow-up list, and the admin "delete this org's data" action."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, g, jsonify

from .. import notifier, serialize, supa
from ..authz import require
from .common import body, mail_row, now, org_settings, text

bp = Blueprint("org", __name__)


# ---------------------------------------------------------------- settings
@bp.get("/settings")
@require("active")
def get_settings():
    return jsonify(serialize.settings(org_settings()))


@bp.put("/settings")
@require("admin")
def put_settings():
    b = body()
    s = org_settings()
    days = dict(s.get("retention_days") or {})
    for t, v in (b.get("retentionDays") or {}).items():
        if t not in serialize.SENDER_TYPES:
            abort(400, f"Unknown sender type: {t}")
        try:
            days[t] = max(1, min(730, int(v)))
        except (TypeError, ValueError):
            abort(400, f"Bad hold days for {t}.")
    s["retention_days"] = days
    if "followupAfterDays" in b:
        try:
            s["followup_after_days"] = max(0, min(90, int(b["followupAfterDays"])))
        except (TypeError, ValueError):
            abort(400, "Bad follow-up days.")
    if "minConfidence" in b:
        try:
            s["min_confidence"] = max(0.0, min(1.0, float(b["minConfidence"])))
        except (TypeError, ValueError):
            abort(400, "Bad confidence threshold.")
    g.db.from_("organizations").update({"settings": s}).eq("id", g.user["orgId"]).execute()
    return jsonify(serialize.settings(s))


# ---------------------------------------------------------------- follow-up list
@bp.get("/followup")
@require("admin")
def followup_list():
    """Urgent mail that is ready for pickup, addressed to a member, and unclaimed for longer
    than the org's followup_after_days."""
    days = int(org_settings().get("followup_after_days", 3))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        g.db.from_("mail_items").select("*").eq("org_id", g.user["orgId"]).eq("urgent", True).eq("status", "ready")
        .not_.is_("member_id", "null").lt("received_at", cutoff).order("received_at").execute().data
    )
    member_ids = list({r["member_id"] for r in rows})
    mail_ids = [r["id"] for r in rows]
    members = {m["id"]: m for m in (g.db.from_("members").select("id, name, phone").in_("id", member_ids).execute().data if member_ids else [])}
    logs = {}
    if mail_ids:
        for entry in g.db.from_("followup_log").select("*").in_("mail_id", mail_ids).order("created_at", desc=True).execute().data:
            logs.setdefault(entry["mail_id"], []).append(entry)
    mails = serialize.mail_list(rows)
    return jsonify({
        "afterDays": days,
        "items": [
            {"mail": m, "member": members.get(r["member_id"]), "attempts": [_log(e) for e in logs.get(r["id"], [])]}
            for r, m in zip(rows, mails)
        ],
    })


def _log(e: dict) -> dict:
    return {k2: e[k1] for k1, k2 in [("id", "id"), ("channel", "channel"), ("simulated", "simulated"), ("outcome", "outcome"),
                                     ("note", "note"), ("created_at", "at"), ("admin_id", "adminId")]}


def _insert_log(mail: dict, channel: str, outcome: str, note: str, simulated: bool) -> dict:
    return g.db.from_("followup_log").insert({
        "org_id": mail["org_id"], "mail_id": mail["id"], "member_id": mail["member_id"], "admin_id": g.user["userId"],
        "channel": channel, "outcome": outcome, "note": note, "simulated": simulated,
    }).execute().data[0]


@bp.post("/followup/<mail_id>/log")
@require("admin")
def followup_log(mail_id):
    """Record a call, visit or other attempt to reach the member."""
    mail = mail_row(mail_id)
    b = body()
    channel = b.get("channel")
    if channel not in ("phone", "in_person", "other", "sms"):
        abort(400, "Bad channel.")
    e = _insert_log(mail, channel, text(b.get("outcome"), 200), text(b.get("note"), 1000), simulated=False)
    return jsonify(_log(e)), 201


@bp.post("/followup/<mail_id>/text")
@require("admin")
def followup_text(mail_id):
    """'Send a text' through the SMS provider. Today that is SimulatedSms: nothing leaves the
    server, and the attempt is logged with simulated = true."""
    mail = mail_row(mail_id)
    msg = text(body().get("body"), 600)
    if not msg:
        abort(400, "Write the text first.")
    m = g.db.from_("members").select("phone").eq("id", mail["member_id"]).limit(1).execute().data
    res = notifier.get_sms().send(m[0]["phone"] if m else "", msg)
    e = _insert_log(mail, "sms", ("sent" if res.ok else "not sent") + (" (simulated)" if res.simulated else ""),
                    f"{msg}\n— {res.detail}", simulated=res.simulated)
    return jsonify(_log(e)), 201


# ---------------------------------------------------------------- danger zone
@bp.post("/org/wipe")
@require("admin")
def wipe_org():
    """Delete this org's mail (and photos), members, requests, messages and member logins.
    Staff logins and settings stay."""
    if body().get("confirm") != "DELETE":
        abort(400, 'Send {"confirm": "DELETE"}.')
    org = g.user["orgId"]
    mails = g.db.from_("mail_items").select("front_image_path, back_image_path, scan_image_paths").eq("org_id", org).execute().data
    supa.remove([p for r in mails for p in serialize.image_paths(r)])
    g.db.from_("mail_items").delete().eq("org_id", org).execute()  # cascades to requests, messages, notifications, follow-ups
    members = g.db.from_("profiles").select("user_id").eq("org_id", org).eq("role", "member").execute().data
    svc = supa.service()
    for p in members:
        svc.auth.admin.delete_user(p["user_id"])  # cascades to the profile
    g.db.from_("members").delete().eq("org_id", org).execute()
    return jsonify({"ok": True, "at": now()})
