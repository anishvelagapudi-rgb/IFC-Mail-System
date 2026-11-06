"""Offline tests for the Claude envelope reader and the local server. No API key or network needed.

    python -m pytest server
"""
from types import SimpleNamespace

import app as server
import pipeline
from pipeline import Extraction

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def _x(**kw):
    base = dict(return_address="DMV, PO Box 1, Raleigh NC", recipient_name="DOT H BRIGGS", sender_name=None, sender_organization="DMV", sender_type="government",
                notes=["Time Sensitive"], urgent=True, legibility="clear", illegible_reason=None, confidence=0.95)
    return Extraction(**{**base, **kw})


def _fake_claude(monkeypatch, resp, seen=None):
    def parse(**kw):
        if seen is not None:
            seen.update(kw)
        return resp
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(pipeline, "_claude", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))


def _resp(parsed, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, parsed_output=parsed, usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_confident_answer_is_kept():
    r = pipeline.apply_confidence(_x())
    assert r["legibility"] == "clear" and r["recipient"]["name"] == "DOT H BRIGGS" and not r["illegible"]


def test_low_confidence_is_flagged_not_guessed():
    r = pipeline.apply_confidence(_x(confidence=0.4))
    assert r["illegible"] and r["recipient"]["name"] == "" and "low confidence" in r["illegible_reason"]
    assert r["notes"] == ["Time Sensitive"] and r["urgent"]


def test_claude_illegible_flag_wins():
    r = pipeline.apply_confidence(_x(legibility="illegible", illegible_reason="heavy blur"))
    assert r["illegible"] and r["illegible_reason"] == "heavy blur"


def test_return_address_name_is_never_used_as_recipient():
    r = pipeline.apply_confidence(_x(recipient_name="Paula Reyes", return_address="Paula Reyes 0110 Suarez Light, Kendrafort WA"))
    assert r["illegible"] and r["recipient"]["name"] == "" and "return address" in r["illegible_reason"]
    r = pipeline.apply_confidence(_x(recipient_name="Paula Reyes", sender_name="PAULA REYES", return_address=None))
    assert r["illegible"]


def test_current_resident_is_kept_not_flagged():
    r = pipeline.apply_confidence(_x(recipient_name="CURRENT RESIDENT", sender_type="junk", confidence=0.9))
    assert not r["illegible"] and r["recipient"]["name"] == "CURRENT RESIDENT"


def test_no_key_means_manual_entry(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = pipeline.read_envelope(JPEG, JPEG)
    assert r["source"] == "manual" and "ANTHROPIC_API_KEY" in r["error"]


def test_refusal_means_manual_entry(monkeypatch):
    _fake_claude(monkeypatch, _resp(None, stop="refusal"))
    assert pipeline.read_envelope(JPEG, JPEG)["source"] == "manual"


def test_sends_both_photos_to_the_model(monkeypatch):
    seen = {}
    _fake_claude(monkeypatch, _resp(_x()), seen)
    r = pipeline.read_envelope(JPEG, JPEG)
    images = [b for b in seen["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 2 and images[0]["source"]["media_type"] == "image/jpeg"
    assert seen["model"] == pipeline.MODEL and seen["output_format"] is Extraction
    assert r["source"] == "claude" and r["recipient"]["name"] == "DOT H BRIGGS"


def test_endpoint_returns_reader_json(monkeypatch):
    _fake_claude(monkeypatch, _resp(_x()))
    c = server.app.test_client()
    from io import BytesIO
    r = c.post("/api/extract", data={"front": (BytesIO(JPEG), "f.jpg"), "back": (BytesIO(JPEG), "b.jpg")})
    assert r.status_code == 200 and r.json["sender"]["organization"] == "DMV"
    assert c.post("/api/extract").status_code == 400
    assert c.get("/").status_code == 200 and c.get("/js/app.js").status_code == 200
