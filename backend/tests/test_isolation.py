"""A member cannot read another member's mail: checked through the API, through RLS alone,
and through the Flask checks alone.

Needs a real Supabase project with the migration applied (use a TEST project, or the local
`supabase start` stack). It creates and deletes its own throwaway org and logins.

    IFC_TEST_SUPABASE=1 python -m pytest backend/tests/test_isolation.py -v
"""
import os
import uuid

import pytest

from backend import config, supa
from backend.app import create_app
from backend.authz import username_to_email

pytestmark = pytest.mark.skipif(
    os.environ.get("IFC_TEST_SUPABASE") != "1" or bool(config.missing()),
    reason="set IFC_TEST_SUPABASE=1 and the SUPABASE_* variables to run against a test project",
)

PASSWORD = "isolation-test-pw-1"


@pytest.fixture(scope="module")
def world():
    svc = supa.service()
    tag = uuid.uuid4().hex[:8]
    org = svc.table("organizations").insert({"name": f"zz-isolation-{tag}"}).execute().data[0]
    other_org = svc.table("organizations").insert({"name": f"zz-isolation-other-{tag}"}).execute().data[0]
    users = []

    def login(username, org_id, role, status, member_id=None):
        u = svc.auth.admin.create_user({"email": username_to_email(username), "password": PASSWORD, "email_confirm": True}).user
        users.append(u.id)
        svc.table("profiles").insert({"user_id": u.id, "org_id": org_id, "role": role, "status": status,
                                      "username": username, "member_id": member_id}).execute()

    def member(org_id, name):
        return svc.table("members").insert({"org_id": org_id, "name": name}).execute().data[0]

    a = member(org["id"], "Alice Isolation")
    b = member(org["id"], "Bob Isolation")
    x = member(other_org["id"], "Xavier Elsewhere")
    login(f"a-{tag}", org["id"], "member", "active", a["id"])
    login(f"b-{tag}", org["id"], "member", "active", b["id"])
    login(f"p-{tag}", org["id"], "member", "pending")
    login(f"adm-{tag}", other_org["id"], "admin", "active")

    mail_a = svc.table("mail_items").insert({"org_id": org["id"], "member_id": a["id"], "recipient_raw": "Alice Isolation",
                                             "sender_org": "Secret Clinic", "status": "ready"}).execute().data[0]
    mail_x = svc.table("mail_items").insert({"org_id": other_org["id"], "member_id": x["id"], "recipient_raw": "Xavier",
                                             "status": "ready"}).execute().data[0]
    svc.table("messages").insert({"org_id": org["id"], "member_id": a["id"], "sender": "staff", "body": "private note for Alice"}).execute()

    yield {"tag": tag, "a": a, "b": b, "mail_a": mail_a, "mail_x": mail_x}

    for uid in users:
        svc.auth.admin.delete_user(uid)
    svc.table("organizations").delete().in_("id", [org["id"], other_org["id"]]).execute()


@pytest.fixture(scope="module")
def client():
    return create_app().test_client()


def token(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.json
    return r.json["access_token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_owner_can_read_own_mail(client, world):
    t = token(client, f"a-{world['tag']}")
    r = client.get(f"/api/mail/{world['mail_a']['id']}", headers=auth(t))
    assert r.status_code == 200 and r.json["sender"]["organization"] == "Secret Clinic"


def test_other_member_cannot_read_mail_via_api(client, world):
    t = token(client, f"b-{world['tag']}")
    mail_id = world["mail_a"]["id"]
    assert client.get(f"/api/mail/{mail_id}", headers=auth(t)).status_code == 404
    assert all(m["id"] != mail_id for m in client.get("/api/mail", headers=auth(t)).json)
    msgs = client.get(f"/api/messages?memberId={world['a']['id']}", headers=auth(t)).json
    assert all(m["memberId"] == world["b"]["id"] for m in msgs)
    assert client.post("/api/requests", json={"mailId": mail_id, "type": "scan"}, headers=auth(t)).status_code == 404
    assert client.patch(f"/api/members/{world['a']['id']}", json={"phone": "x"}, headers=auth(t)).status_code == 404
    assert client.get(f"/api/members/{world['a']['id']}", headers=auth(t)).status_code == 404


def test_rls_alone_blocks_other_member(client, world):
    """Bypass Flask: query PostgREST directly with Bob's JWT."""
    db = supa.user_db(token(client, f"b-{world['tag']}"))
    assert db.from_("mail_items").select("*").eq("id", world["mail_a"]["id"]).execute().data == []
    assert db.from_("messages").select("*").eq("member_id", world["a"]["id"]).execute().data == []
    assert db.from_("members").select("*").eq("id", world["a"]["id"]).execute().data == []
    with pytest.raises(Exception):
        db.from_("requests").insert({"org_id": world["mail_a"]["org_id"], "mail_id": world["mail_a"]["id"],
                                     "member_id": world["a"]["id"], "type": "scan"}).execute()


def test_flask_alone_blocks_other_member(client, world, monkeypatch):
    """Bypass RLS: give the routes a service-role database client. Flask's own scoping must still hold."""
    from postgrest import SyncPostgrestClient

    def unrestricted(_token):
        return SyncPostgrestClient(f"{config.SUPABASE_URL}/rest/v1", headers={
            "apikey": config.SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"})

    t = token(client, f"b-{world['tag']}")
    monkeypatch.setattr(supa, "user_db", unrestricted)
    mail_id = world["mail_a"]["id"]
    assert client.get(f"/api/mail/{mail_id}", headers=auth(t)).status_code == 404
    assert all(m["id"] != mail_id for m in client.get("/api/mail", headers=auth(t)).json)
    assert client.post("/api/requests", json={"mailId": mail_id, "type": "scan"}, headers=auth(t)).status_code == 404


def test_pending_account_sees_nothing(client, world):
    t = token(client, f"p-{world['tag']}")
    assert client.get("/api/me", headers=auth(t)).json["status"] == "pending"
    assert client.get("/api/mail", headers=auth(t)).status_code == 403
    assert supa.user_db(t).from_("mail_items").select("id").execute().data == []


def test_admin_cannot_read_other_orgs_mail(client, world):
    t = token(client, f"adm-{world['tag']}")
    assert client.get(f"/api/mail/{world['mail_a']['id']}", headers=auth(t)).status_code == 404
    ids = {m["id"] for m in client.get("/api/mail", headers=auth(t)).json}
    assert world["mail_x"]["id"] in ids and world["mail_a"]["id"] not in ids
