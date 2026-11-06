"""Mail items: scan (upload + pipeline), review, confirm, close/discard, scans, notifications."""
import uuid

from flask import Blueprint, abort, g, jsonify, request

from .. import matching, pipeline, serialize, supa
from ..authz import is_admin, require
from .common import body, mail_row, member_ids_in_org, now, org_settings, text, text_list, uuid_or_none

bp = Blueprint("mail", __name__)


def _file(name: str) -> bytes:
    f = request.files.get(name)
    if not f:
        abort(400, f"Missing the {name} photo.")
    data = f.read()
    if not data:
        abort(400, f"The {name} photo is empty.")
    try:
        pipeline._media_type(data)
    except ValueError as e:
        abort(400, str(e))
    return data


def _min_confidence() -> float:
    try:
        return float(org_settings().get("min_confidence", 0.7))
    except (TypeError, ValueError):
        return 0.7


@bp.get("/mail")
@require("active")
def list_mail():
    q = g.db.from_("mail_items").select("*").eq("org_id", g.user["orgId"])
    if not is_admin():
        q = q.eq("member_id", g.user["memberId"]).neq("status", "needs_review")
    return jsonify(serialize.mail_list(q.order("received_at", desc=True).execute().data))


@bp.get("/mail/<mail_id>")
@require("active")
def get_mail(mail_id):
    return jsonify(serialize.mail(mail_row(mail_id)))


@bp.post("/mail")
@require("admin")
def create_mail():
    """Staff scanned an envelope: store both photos privately, run the pipeline, try to match
    the recipient, and save the item as needs_review (a person confirms before notifying)."""
    front, back = _file("front"), _file("back")
    org_id = g.user["orgId"]
    mail_id = str(uuid.uuid4())
    paths = {"front": f"{org_id}/{mail_id}/front.jpg", "back": f"{org_id}/{mail_id}/back.jpg"}
    supa.upload(paths["front"], front, pipeline._media_type(front))
    supa.upload(paths["back"], back, pipeline._media_type(back))

    try:
        result = pipeline.extract(front, back, _min_confidence())
        member = None
        if result["recipient"]["name"] and result["legibility"] != "illegible":
            members = g.db.from_("members").select("id, name, aliases").eq("org_id", org_id).execute().data
            member = matching.match(result["recipient"]["name"], members)
        result["processing"]["matched"] = bool(member)
        row = g.db.from_("mail_items").insert({
            "id": mail_id,
            "org_id": org_id,
            "member_id": member["id"] if member else None,
            "recipient_raw": result["recipient"]["name"],
            "sender_name": result["sender"]["name"],
            "sender_org": result["sender"]["organization"],
            "sender_type": result["sender"]["sender_type"] if result["sender"]["sender_type"] in serialize.SENDER_TYPES else "unknown",
            "notes": result["notes"],
            "legibility": result["legibility"],
            "illegible_reason": result["illegible_reason"],
            "confidence": result["confidence"],
            "front_image_path": paths["front"],
            "back_image_path": paths["back"],
            "extraction": {"processing": result["processing"], "model": result["model"], "usage": result.get("usage")},
            "status": "needs_review",
        }).execute().data[0]
    except Exception:
        supa.remove(list(paths.values()))  # don't leave orphaned photos
        raise
    return jsonify(serialize.mail(row)), 201


@bp.post("/pipeline/extract")
@require("admin")
def extract_only():
    """Run the pipeline on two photos without saving anything (testing / re-checks)."""
    result = pipeline.extract(_file("front"), _file("back"), _min_confidence())
    return jsonify(pipeline.for_client(result))


@bp.patch("/mail/<mail_id>")
@require("admin")
def update_mail(mail_id):
    """Staff corrections from the review screen. Status changes go through confirm/close."""
    row = mail_row(mail_id)
    b = body()
    upd = {}
    s = b.get("sender")
    if isinstance(s, dict):
        upd["sender_name"] = text(s.get("name"), 200)
        upd["sender_org"] = text(s.get("organization"), 200)
        t = s.get("type") or "unknown"
        if t not in serialize.SENDER_TYPES:
            abort(400, "Unknown sender type.")
        upd["sender_type"] = t
    r = b.get("recipient")
    if isinstance(r, dict):
        upd["recipient_raw"] = text(r.get("name"), 200)
        mid = uuid_or_none(r.get("memberId"))
        if mid and mid not in member_ids_in_org([mid]):
            abort(400, "That member is not in your organization.")
        upd["member_id"] = mid
    if "notes" in b:
        upd["notes"] = text_list(b["notes"], 20, 200)
    if "legibility" in b:
        if b["legibility"] not in (None, "", "clear", "degraded", "illegible"):
            abort(400, "Bad legibility value.")
        upd["legibility"] = b["legibility"] or None
    if "illegibleReason" in b:
        upd["illegible_reason"] = text(b["illegibleReason"], 200) or None
    if b.get("receivedAt"):
        upd["received_at"] = text(b["receivedAt"], 40)
    if "extraDays" in b:
        try:
            upd["extra_days"] = max(0, min(365, int(b["extraDays"] or 0)))
        except (TypeError, ValueError):
            abort(400, "Bad extra days value.")
    if not upd:
        return jsonify(serialize.mail(row))
    row = g.db.from_("mail_items").update(upd).eq("id", row["id"]).execute().data[0]
    return jsonify(serialize.mail(row))


@bp.post("/mail/<mail_id>/confirm")
@require("admin")
def confirm(mail_id):
    """Staff checked the details: mark ready for pickup and notify the recipient (once)."""
    row = mail_row(mail_id)
    upd = {"status": "ready"} if row["status"] == "needs_review" else {}
    if row["member_id"] and not row["notified_at"]:
        m = g.db.from_("members").select("phone").eq("id", row["member_id"]).limit(1).execute().data
        sender = row["sender_org"] or row["sender_name"] or "an unknown sender"
        g.db.from_("notifications").insert({
            "org_id": row["org_id"],
            "mail_id": row["id"],
            "member_id": row["member_id"],
            "channels": ["app", "sms"] if m and m[0]["phone"] else ["app"],
            "body": f"You have new mail from {sender}. Please pick it up.",
            "status": "queued",
        }).execute()
        upd["notified_at"] = now()
    if upd:
        row = g.db.from_("mail_items").update(upd).eq("id", row["id"]).execute().data[0]
    return jsonify(serialize.mail(row))


@bp.post("/mail/<mail_id>/close")
@require("admin")
def close(mail_id):
    row = mail_row(mail_id)
    b = body()
    outcome = b.get("outcome")
    if outcome not in ("picked_up", "redirected", "discarded"):
        abort(400, "Bad outcome.")
    upd = {"status": "closed", "outcome": outcome, "closed_at": now()}
    if outcome == "redirected":
        upd["redirected_to"] = text(b.get("redirectedTo"), 300)
    if outcome == "discarded":
        # Privacy: delete the photos and scans; keep a minimal record for audit.
        supa.remove(serialize.image_paths(row))
        upd.update({"front_image_path": None, "back_image_path": None, "scan_image_paths": []})
    row = g.db.from_("mail_items").update(upd).eq("id", row["id"]).execute().data[0]
    return jsonify(serialize.mail(row))


@bp.post("/mail/<mail_id>/scans")
@require("admin")
def add_scan(mail_id):
    """A photo of the contents, for a member who asked for one."""
    row = mail_row(mail_id)
    data = _file("file")
    path = f"{row['org_id']}/{row['id']}/scan-{uuid.uuid4().hex[:8]}.jpg"
    supa.upload(path, data, pipeline._media_type(data))
    row = g.db.from_("mail_items").update({"scan_image_paths": [*(row["scan_image_paths"] or []), path]}).eq("id", row["id"]).execute().data[0]
    return jsonify(serialize.mail(row)), 201


@bp.get("/mail/<mail_id>/notifications")
@require("admin")
def notifications(mail_id):
    row = mail_row(mail_id)
    rows = g.db.from_("notifications").select("*").eq("mail_id", row["id"]).order("created_at").execute().data
    return jsonify([serialize.notification(n) for n in rows])
