"""Envelope image pipeline: front + back photo -> structured fields, via Claude vision.

The model returns strict JSON (structured outputs). If it isn't confident, or says the
envelope is unreadable, the item is marked illegible for manual review instead of guessed at.
Any failure (no API key, network, refusal) falls back to manual entry so no photo is lost.

The result uses the same shape as the dataset-generator labels / web/js/pipeline.js:
    {legibility, illegible_reason, sender{name, organization, sender_type}, recipient{name},
     notes[], urgent, confidence, processing{source, model, error?}, model{...raw...}}
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

from . import config

log = logging.getLogger(__name__)

SenderType = Literal["government", "bank", "healthcare", "employer", "personal", "junk", "unknown"]


class Extraction(BaseModel):
    recipient_name: Optional[str]
    sender_name: Optional[str]
    sender_organization: Optional[str]
    sender_type: SenderType
    notes: list[str]
    urgent: bool
    legibility: Literal["clear", "degraded", "illegible"]
    illegible_reason: Optional[str]
    confidence: float


SYSTEM = """You read photos of envelopes that arrived at a homeless shelter's mail program, so staff can tell \
each person their mail is waiting. You get two photos: the FRONT of the envelope, then the BACK.

Return these fields:
- recipient_name: the addressee's name exactly as printed or written (keep spelling and capitalisation). \
Only the person's name: no "c/o" line, street address, or organization. null if there is no name you can read.
- sender_name: the person named in the return address, as printed. null if none (e.g. only an organization).
- sender_organization: the company or agency in the return address, as printed (no department line). null if none.
- sender_type: government, bank, healthcare, employer, personal (a private individual), junk (advertising, \
"Current Resident", promotions), or unknown.
- notes: printed or stamped endorsements, exactly as written, e.g. "Time Sensitive", "Return Service Requested", \
"Final Notice", "Open Immediately", "Important Tax Document". Not postage, barcodes, or addresses. Empty list if none.
- urgent: true if the markings or the sender suggest a deadline (court, hearing, final notice, time sensitive, \
benefits renewal, jury duty).
- legibility: clear (easy to read), degraded (readable with effort: blur, glare, damage, handwriting), or \
illegible (you cannot read the recipient name reliably).
- illegible_reason: a few words if legibility is illegible (e.g. "heavy blur", "name covered"), else null.
- confidence: 0 to 1, how sure you are that recipient_name is exactly right.

Never guess. A wrong name sends someone's mail to the wrong person; a blank field just means staff look at it. \
If you are unsure of a field, return null and lower your confidence."""

MAX_IMAGE_BYTES = 4_500_000  # stay under the API's per-image limit after base64


def _media_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise ValueError("Photos must be JPEG, PNG, WebP or GIF.")


def _shrink(data: bytes) -> bytes:
    """Re-encode very large photos so they fit the API limit."""
    if len(data) <= MAX_IMAGE_BYTES:
        return data
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((2000, 2000))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _image_block(data: bytes) -> dict:
    data = _shrink(data)
    return {"type": "image", "source": {"type": "base64", "media_type": _media_type(data), "data": base64.standard_b64encode(data).decode()}}


def manual(error: str | None = None) -> dict:
    proc = {"source": "manual"}
    if error:
        proc["error"] = error
    return {
        "processing": proc,
        "model": None,
        "legibility": None,
        "illegible_reason": None,
        "sender": {"name": "", "organization": "", "sender_type": "unknown"},
        "recipient": {"name": ""},
        "notes": [],
        "urgent": False,
        "confidence": None,
    }


def apply_confidence(x: Extraction, min_confidence: float) -> dict:
    """Turn a model answer into a pipeline result, refusing to guess when unsure."""
    conf = max(0.0, min(1.0, float(x.confidence)))
    result = {
        "legibility": x.legibility,
        "illegible_reason": x.illegible_reason,
        "sender": {"name": x.sender_name or "", "organization": x.sender_organization or "", "sender_type": x.sender_type},
        "recipient": {"name": (x.recipient_name or "").strip()},
        "notes": [n.strip() for n in x.notes if n and n.strip()],
        "urgent": bool(x.urgent),
        "confidence": conf,
    }
    if x.legibility == "illegible" or conf < min_confidence or not result["recipient"]["name"]:
        result["legibility"] = "illegible"
        result["illegible_reason"] = x.illegible_reason or (
            "no readable recipient name" if not result["recipient"]["name"] else f"low confidence ({conf:.2f})"
        )
        # Don't guess: keep the raw answer in `model` for staff, but leave the fields blank.
        result["recipient"] = {"name": ""}
        result["sender"] = {"name": "", "organization": "", "sender_type": "unknown"}
    return result


_client = None


def _anthropic() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60.0, max_retries=2)
    return _client


def extract(front: bytes, back: bytes, min_confidence: float = 0.7) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return manual("ANTHROPIC_API_KEY is not set")
    try:
        content = [
            {"type": "text", "text": "FRONT of the envelope:"},
            _image_block(front),
            {"type": "text", "text": "BACK of the envelope:"},
            _image_block(back),
            {"type": "text", "text": "Extract the fields."},
        ]
    except Exception as e:  # unreadable upload
        return manual(str(e))

    try:
        resp = _anthropic().messages.parse(
            model=config.PIPELINE_MODEL,
            max_tokens=4096,
            system=SYSTEM,
            output_config={"effort": "low"},
            output_format=Extraction,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.RateLimitError:
        return manual("pipeline is busy (rate limited), enter details by hand")
    except anthropic.APIConnectionError:
        return manual("could not reach the pipeline")
    except anthropic.APIStatusError as e:
        log.warning("pipeline API error %s: %s", e.status_code, e.message)
        return manual(f"pipeline error {e.status_code}")
    except Exception as e:  # schema validation etc.
        log.exception("pipeline failed")
        return manual(f"pipeline failed: {type(e).__name__}")

    meta = {"model": resp.model, "request_id": resp._request_id, "stop_reason": resp.stop_reason}
    if resp.stop_reason == "refusal":
        out = manual("the model declined to read this item")
        out["processing"].update(meta)
        return out
    x = resp.parsed_output
    if x is None:
        out = manual(f"no usable answer (stop reason: {resp.stop_reason})")
        out["processing"].update(meta)
        return out
    meta["source"] = "pipeline"

    result = apply_confidence(x, min_confidence)
    result["processing"] = meta
    result["model"] = x.model_dump()
    result["usage"] = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return result


def for_client(result: dict) -> dict:
    """The JSON shape web/js/pipeline.js and dataset-generator/evaluate.py read."""
    return {
        "legibility": result["legibility"],
        "illegible": result["legibility"] == "illegible",
        "illegible_reason": result["illegible_reason"],
        "sender": result["sender"],
        "recipient": result["recipient"],
        "notes": result["notes"],
        "urgent": result["urgent"],
        "confidence": result["confidence"],
        "processing": result["processing"],
    }
