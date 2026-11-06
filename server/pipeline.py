"""Read an envelope (front + back photo) with Claude.

Returns strict JSON in the same shape as the dataset-generator labels, which is what
web/js/pipeline.js expects. If Claude isn't confident, or says the envelope is unreadable,
the result is marked illegible with blank fields instead of a guess. If there's no API key or
anything goes wrong, it returns a "manual" result so staff just type the details in.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

# Cheapest Claude model that can read images. Override with PIPELINE_MODEL in .env if you like.
MODEL = os.environ.get("PIPELINE_MODEL") or "claude-haiku-5-5"
MIN_CONFIDENCE = 0.7  # below this, flag illegible instead of guessing
MAX_IMAGE_BYTES = 4_500_000

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
- sender_name: the person named in the return address, as written, including any title such as "Dr." \
Read handwritten return names too when you can make them out; null only if there is no person's name or you \
genuinely cannot read it.
- sender_organization: the company or agency in the return address, as printed (no department line). null if none.
- sender_type: government, bank, healthcare, employer, personal (a private individual), junk (advertising, \
"Current Resident", promotions), or unknown.
- notes: endorsements and messages on the envelope, printed, stamped or handwritten, exactly as written, e.g. \
"Time Sensitive", "Return Service Requested", "Final Notice", "Open Immediately", "please call me". \
Do NOT include postage or mail-class printing ("Presorted First-Class Mail", "U.S. Postage Paid", "Permit No."), \
barcodes, or addresses. Empty list if none.
- urgent: true if the markings or the sender suggest a deadline (court, hearing, final notice, time sensitive, \
benefits renewal, jury duty).
- legibility: clear (easy to read), degraded (readable with effort: blur, glare, damage, handwriting), or \
illegible (you cannot read the recipient name reliably).
- illegible_reason: a few words if legibility is illegible (e.g. "heavy blur", "name covered"), else null.
- confidence: 0 to 1, how sure you are that recipient_name is exactly right.

Never guess. A wrong name sends someone's mail to the wrong person; a blank field just means staff look at it. \
If you are unsure of a field, return null and lower your confidence."""


def media_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Photos must be JPEG, PNG or WebP.")


def _image(data: bytes) -> dict:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Photo is too large (over 4.5 MB).")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type(data), "data": base64.standard_b64encode(data).decode()}}


def manual(error: str | None = None) -> dict:
    return {
        "source": "manual",
        **({"error": error} if error else {}),
        "legibility": None,
        "illegible_reason": None,
        "sender": {"name": "", "organization": "", "sender_type": "unknown"},
        "recipient": {"name": ""},
        "notes": [],
        "urgent": False,
        "confidence": None,
    }


def apply_confidence(x: Extraction, min_confidence: float = MIN_CONFIDENCE) -> dict:
    """Turn Claude's answer into a result, refusing to guess when unsure."""
    conf = max(0.0, min(1.0, float(x.confidence)))
    r = {
        "source": "claude",
        "legibility": x.legibility,
        "illegible": False,
        "illegible_reason": x.illegible_reason,
        "sender": {"name": x.sender_name or "", "organization": x.sender_organization or "", "sender_type": x.sender_type},
        "recipient": {"name": (x.recipient_name or "").strip()},
        "notes": [n.strip() for n in x.notes if n and n.strip()],
        "urgent": bool(x.urgent),
        "confidence": conf,
    }
    if x.legibility == "illegible" or conf < min_confidence or not r["recipient"]["name"]:
        r["legibility"] = "illegible"
        r["illegible"] = True
        r["illegible_reason"] = x.illegible_reason or (
            "no readable recipient name" if not r["recipient"]["name"] else f"low confidence ({conf:.2f})"
        )
        r["recipient"] = {"name": ""}
        r["sender"] = {"name": "", "organization": "", "sender_type": "unknown"}
        # notes and urgent are kept: a "Final Notice" stamp still tells staff to look soon.
    return r


_client = None


def _claude() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=60.0, max_retries=2)  # reads ANTHROPIC_API_KEY
    return _client


def read_envelope(front: bytes, back: bytes) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return manual("no ANTHROPIC_API_KEY in .env, so enter the details by hand")
    try:
        content = [
            {"type": "text", "text": "FRONT of the envelope:"},
            _image(front),
            {"type": "text", "text": "BACK of the envelope:"},
            _image(back),
            {"type": "text", "text": "Extract the fields."},
        ]
    except ValueError as e:
        return manual(str(e))

    try:
        resp = _claude().messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            output_config={"effort": "low"},
            output_format=Extraction,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError:
        return manual("the API key in .env was rejected")
    except anthropic.RateLimitError:
        return manual("Claude is busy (rate limited)")
    except anthropic.APIConnectionError:
        return manual("could not reach Claude (check your internet connection)")
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s: %s", e.status_code, e.message)
        return manual(f"Claude returned error {e.status_code}")

    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return manual(f"Claude gave no usable answer ({resp.stop_reason})")
    result = apply_confidence(resp.parsed_output)
    result["raw"] = resp.parsed_output.model_dump()
    result["usage"] = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return result
