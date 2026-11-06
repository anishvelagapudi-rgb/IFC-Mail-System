"""Offline tests: recipient matching and the pipeline's "don't guess" rule. No network needed."""
from types import SimpleNamespace

from backend import config, matching, pipeline
from backend.pipeline import Extraction

MEMBERS = [
    {"id": "dot", "name": "Dorothy Briggs", "aliases": ["Dot Briggs", "Dorothy H Briggs"]},
    {"id": "bill", "name": "William Ortiz", "aliases": ["Bill Ortiz"]},
    {"id": "renee", "name": "Renee Carter", "aliases": []},
]


def test_exact_and_alias_match_any_order():
    assert matching.match("BRIGGS, DOROTHY", MEMBERS)["id"] == "dot"
    assert matching.match("Dot H. Briggs", MEMBERS)["id"] == "dot"  # fuzzy, near the "Dot Briggs" alias
    assert matching.match("bill ortiz", MEMBERS)["id"] == "bill"


def test_fuzzy_only_with_clear_winner():
    assert matching.match("Renee Cartr", MEMBERS)["id"] == "renee"
    assert matching.match("Current Resident", MEMBERS) is None
    assert matching.match("", MEMBERS) is None


def test_duplicate_names_are_not_auto_matched():
    twins = MEMBERS + [{"id": "dot2", "name": "Dorothy Briggs", "aliases": []}]
    assert matching.match("Dorothy Briggs", twins) is None


def _x(**kw):
    base = dict(recipient_name="DOT H BRIGGS", sender_name=None, sender_organization="DMV", sender_type="government",
                notes=["Time Sensitive"], urgent=True, legibility="clear", illegible_reason=None, confidence=0.95)
    return Extraction(**{**base, **kw})


def test_confident_answer_is_kept():
    r = pipeline.apply_confidence(_x(), 0.7)
    assert r["legibility"] == "clear" and r["recipient"]["name"] == "DOT H BRIGGS" and r["urgent"]


def test_low_confidence_becomes_illegible_without_a_guess():
    r = pipeline.apply_confidence(_x(confidence=0.4), 0.7)
    assert r["legibility"] == "illegible" and r["recipient"]["name"] == "" and "low confidence" in r["illegible_reason"]
    assert r["notes"] == ["Time Sensitive"]  # endorsements still help staff prioritise


def test_model_illegible_flag_wins():
    r = pipeline.apply_confidence(_x(legibility="illegible", illegible_reason="heavy blur", confidence=0.9), 0.7)
    assert r["legibility"] == "illegible" and r["illegible_reason"] == "heavy blur"


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def test_no_api_key_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    r = pipeline.extract(JPEG, JPEG)
    assert r["processing"]["source"] == "manual" and "ANTHROPIC_API_KEY" in r["processing"]["error"]


def test_refusal_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test")
    resp = SimpleNamespace(stop_reason="refusal", parsed_output=None, model="m", _request_id="req_1",
                           usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    fake = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: resp))
    monkeypatch.setattr(pipeline, "_anthropic", lambda: fake)
    r = pipeline.extract(JPEG, JPEG)
    assert r["processing"]["source"] == "manual" and r["legibility"] is None


def test_request_shape_sends_both_images(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test")
    seen = {}

    def parse(**kw):
        seen.update(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=_x(), model=kw["model"], _request_id="req_2",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    monkeypatch.setattr(pipeline, "_anthropic", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    r = pipeline.extract(JPEG, JPEG)
    images = [b for b in seen["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 2 and images[0]["source"]["media_type"] == "image/jpeg"
    assert seen["model"] == config.PIPELINE_MODEL and seen["output_format"] is Extraction
    assert r["processing"]["source"] == "pipeline" and r["model"]["recipient_name"] == "DOT H BRIGGS"
