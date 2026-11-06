"""Create the demo organization, logins and sample mail so the demo works out of the box.

    python -m backend.seed            # create anything missing (safe to re-run)
    python -m backend.seed --reset    # delete the demo org and its logins first

Logins (passwords from SEED_ADMIN_PASSWORD / SEED_MEMBER_PASSWORD, else these defaults):
    staff   / staff123     org admin
    dorothy / dorothy123   member (Dorothy Briggs)

Sample data only: envelope images are drawn placeholders, never real mail.
"""
import argparse
import io
import os
import sys
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

from . import config, supa
from .authz import username_to_email

ORG_NAME = "IFC Demo Shelter (sample data)"


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def envelope(lines: list[str], side: str) -> bytes:
    img = Image.new("RGB", (800, 560), "#6b5b4b")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 760, 520], fill="#f4efe6", outline="#c9c0b0")
    d.text((60, 55), f"SAMPLE - {side}", fill="#222", font=_font(22))
    x, y = (260, 240) if side == "front" else (80, 140)
    for i, line in enumerate(lines):
        d.text((x, y + i * 40), line, fill="#222", font=_font(28))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


def ensure_login(svc, org_id, username, password, role, display_name, member_id=None):
    existing = svc.table("profiles").select("user_id").eq("username", username).execute().data
    if existing:
        return existing[0]["user_id"]
    user = svc.auth.admin.create_user({"email": username_to_email(username), "password": password, "email_confirm": True,
                                       "user_metadata": {"username": username}}).user
    svc.table("profiles").insert({
        "user_id": user.id, "org_id": org_id, "role": role, "status": "active", "username": username,
        "display_name": display_name, "member_id": member_id, "approved_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return user.id


def reset(svc):
    orgs = svc.table("organizations").select("id").eq("name", ORG_NAME).execute().data
    for o in orgs:
        mail = svc.table("mail_items").select("front_image_path, back_image_path, scan_image_paths").eq("org_id", o["id"]).execute().data
        supa.remove([p for r in mail for p in [r["front_image_path"], r["back_image_path"], *(r["scan_image_paths"] or [])]])
        for p in svc.table("profiles").select("user_id").eq("org_id", o["id"]).execute().data:
            svc.auth.admin.delete_user(p["user_id"])
        svc.table("organizations").delete().eq("id", o["id"]).execute()
    print(f"Removed {len(orgs)} demo org(s).")


def seed(svc):
    org = svc.table("organizations").select("id").eq("name", ORG_NAME).execute().data
    if org:
        org_id = org[0]["id"]
        print(f"Demo org exists ({org_id}); adding anything missing.")
    else:
        org_id = svc.table("organizations").insert({"name": ORG_NAME}).execute().data[0]["id"]
        print(f"Created demo org {org_id}.")

    ensure_login(svc, org_id, "staff", os.environ.get("SEED_ADMIN_PASSWORD") or "staff123", "admin", "Demo Staff")

    if svc.table("members").select("id").eq("org_id", org_id).limit(1).execute().data:
        print("Sample members/mail already present.")
        dot = svc.table("members").select("id").eq("org_id", org_id).eq("name", "Dorothy Briggs").execute().data[0]
        ensure_login(svc, org_id, "dorothy", os.environ.get("SEED_MEMBER_PASSWORD") or "dorothy123", "member", "Dorothy Briggs", dot["id"])
        return

    def member(name, aliases, phone):
        return svc.table("members").insert({"org_id": org_id, "name": name, "aliases": aliases, "phone": phone}).execute().data[0]

    dot = member("Dorothy Briggs", ["Dot Briggs", "Dorothy H Briggs"], "919-555-0101")
    bill = member("William Ortiz", ["Bill Ortiz"], "")
    member("Renee Carter", [], "919-555-0177")
    svc.table("trusted_contacts").insert({"org_id": org_id, "member_id": dot["id"], "name": "Marcus Lee", "relationship": "case manager",
                                          "phone": "919-555-0140", "address": "210 Weaver St, Carrboro, NC 27510"}).execute()
    ensure_login(svc, org_id, "dorothy", os.environ.get("SEED_MEMBER_PASSWORD") or "dorothy123", "member", "Dorothy Briggs", dot["id"])
    svc.table("members").update({"registered_at": datetime.now(timezone.utc).isoformat()}).eq("id", dot["id"]).execute()

    now = datetime.now(timezone.utc)
    items = [
        # age (days), sender org, type, addressed to, member, notes, legibility, status
        (5, "Department of Motor Vehicles", "government", "Dot Briggs", dot, ["TIME SENSITIVE"], "clear", "ready"),
        (40, "Summit Community Bank", "bank", "Bill Ortiz", bill, ["Return Service Requested"], "degraded", "ready"),
        (1, "", "unknown", "", None, [], "illegible", "needs_review"),
        (10, "Carolina Furniture Outlet", "junk", "Current Resident", None, [], "clear", "ready"),
        (70, "County Housing Authority", "government", "Dorothy Briggs", dot, ["IMPORTANT INFORMATION ENCLOSED"], "clear", "ready"),
    ]
    for age, sender, kind, to, m, notes, legib, status in items:
        mail_id = svc.table("mail_items").insert({
            "org_id": org_id, "member_id": m["id"] if m else None, "recipient_raw": to, "sender_org": sender, "sender_type": kind,
            "notes": notes, "legibility": legib, "status": status, "received_at": (now - timedelta(days=age)).isoformat(),
            "illegible_reason": "sample: unreadable" if legib == "illegible" else None,
            "extraction": {"processing": {"source": "seed"}}, "notified_at": now.isoformat() if (m and status == "ready") else None,
        }).execute().data[0]["id"]
        front = f"{org_id}/{mail_id}/front.jpg"
        back = f"{org_id}/{mail_id}/back.jpg"
        supa.upload(front, envelope([sender or "(unreadable)", "", f"TO: {to or '???'}", "c/o DEMO SHELTER", "CHAPEL HILL, NC"], "front"))
        supa.upload(back, envelope(["(flap)"], "back"))
        svc.table("mail_items").update({"front_image_path": front, "back_image_path": back}).eq("id", mail_id).execute()
        if m and status == "ready":
            svc.table("notifications").insert({"org_id": org_id, "mail_id": mail_id, "member_id": m["id"], "channels": ["app"],
                                               "body": f"You have new mail from {sender}. Please pick it up.", "status": "queued"}).execute()

    svc.table("messages").insert({"org_id": org_id, "member_id": dot["id"], "sender": "member", "seen_by_member": True,
                                  "body": "Hi, can someone tell me when the DMV letter came in?"}).execute()
    print("Added 3 members, 5 sample mail items, 1 message.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete the demo org and its logins first")
    args = ap.parse_args()
    if config.missing():
        sys.exit(f"Set {', '.join(config.missing())} (see .env.example).")
    svc = supa.service()
    if args.reset:
        reset(svc)
    seed(svc)
    print("Logins: staff / staff123 (admin), dorothy / dorothy123 (member)")


if __name__ == "__main__":
    main()
