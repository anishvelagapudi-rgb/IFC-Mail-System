"""Database rows -> the JSON shapes the existing web app already uses (see web/js/store.js)."""
from . import supa

SENDER_TYPES = ("government", "bank", "healthcare", "employer", "personal", "junk", "unknown")


def image_paths(row: dict) -> list[str]:
    return [row.get("front_image_path"), row.get("back_image_path"), *(row.get("scan_image_paths") or [])]


def mail_list(rows: list[dict]) -> list[dict]:
    """Serialize mail rows, signing every photo in one Storage call.

    The web app reads photos through store.getImageUrl(frontImageId); here the "image id" IS a
    short-lived signed URL, so the views need no changes.
    """
    urls = supa.sign([p for r in rows for p in image_paths(r)])
    return [mail(r, urls) for r in rows]


def mail(r: dict, urls: dict[str, str] | None = None) -> dict:
    if urls is None:
        urls = supa.sign(image_paths(r))
    ext = r.get("extraction") or {}
    return {
        "id": r["id"],
        "orgId": r["org_id"],
        "receivedAt": r["received_at"],
        "frontImageId": urls.get(r.get("front_image_path") or ""),
        "backImageId": urls.get(r.get("back_image_path") or ""),
        "scanImageIds": [urls[p] for p in (r.get("scan_image_paths") or []) if p in urls],
        "sender": {"name": r["sender_name"], "organization": r["sender_org"], "type": r["sender_type"]},
        "recipient": {"name": r["recipient_raw"], "memberId": r.get("member_id")},
        "notes": r.get("notes") or [],
        "urgent": r.get("urgent", False),
        "legibility": r.get("legibility"),
        "illegible": r.get("illegible", False),
        "illegibleReason": r.get("illegible_reason"),
        "confidence": r.get("confidence"),
        "processing": ext.get("processing") or {"source": "manual"},
        "status": r["status"],
        "outcome": r.get("outcome"),
        "extraDays": r.get("extra_days", 0),
        "holdUntil": r.get("hold_until"),
        "redirectedTo": r.get("redirected_to"),
        "closedAt": r.get("closed_at"),
        "notifiedAt": r.get("notified_at"),
    }


def contact(c: dict) -> dict:
    return {k: c.get(k, "") for k in ("id", "name", "relationship", "phone", "address")}


def member(m: dict, contacts: list[dict], account: dict | None = None) -> dict:
    return {
        "id": m["id"],
        "orgId": m["org_id"],
        "name": m["name"],
        "aliases": m.get("aliases") or [],
        "phone": m.get("phone") or "",
        "email": m.get("email") or "",
        "trustedContacts": [contact(c) for c in contacts],
        "userId": account["user_id"] if account else None,
        "registeredAt": m.get("registered_at"),
    }


def request_(r: dict) -> dict:
    return {
        "id": r["id"],
        "orgId": r["org_id"],
        "mailId": r["mail_id"],
        "memberId": r["member_id"],
        "type": r["type"],
        "status": r["status"],
        "payload": r.get("payload") or {},
        "createdAt": r["created_at"],
        "resolvedAt": r.get("resolved_at"),
    }


def message(m: dict) -> dict:
    return {
        "id": m["id"],
        "orgId": m["org_id"],
        "memberId": m["member_id"],
        "mailId": m.get("mail_id"),
        "requestId": m.get("request_id"),
        "from": m["sender"],
        "body": m["body"],
        "at": m["created_at"],
        "seenByStaff": m["seen_by_staff"],
        "seenByMember": m["seen_by_member"],
    }


def notification(n: dict) -> dict:
    return {
        "id": n["id"],
        "mailId": n["mail_id"],
        "memberId": n["member_id"],
        "channels": n.get("channels") or [],
        "body": n["body"],
        "status": n["status"],
        "at": n["created_at"],
    }


def account(p: dict) -> dict:
    return {
        "id": p["user_id"],
        "username": p["username"],
        "name": p.get("display_name") or "",
        "role": p["role"],
        "status": p["status"],
        "memberId": p.get("member_id"),
        "registration": p.get("registration") or {},
        "createdAt": p["created_at"],
    }


def settings(s: dict) -> dict:
    return {
        "retentionDays": dict(s.get("retention_days") or {}),
        "followupAfterDays": s.get("followup_after_days", 3),
        "minConfidence": s.get("min_confidence", 0.7),
    }
