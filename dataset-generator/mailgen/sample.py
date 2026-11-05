"""Generate one complete sample (front + back images, label JSON, manifest row)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from faker import Faker
from PIL import Image

from . import degrade
from .augment import local_scale, photograph, rect_poly, transform_points, visible_fraction
from .config import augment_preset
from .content import MailContent, chance, weighted
from .envelope import Rendered, choose_spec, render_back, render_front
from .fonts import pick_font

_FAKER: Faker | None = None


def _faker(seed: int) -> Faker:
    global _FAKER
    if _FAKER is None:
        _FAKER = Faker("en_US")
    _FAKER.seed_instance(seed)
    return _FAKER


def make_sheet(env: Image.Image, pad: int) -> tuple[np.ndarray, int]:
    """Place the envelope on a transparent, padded canvas (padding leaves room for an overlapping envelope)."""
    W, H = env.size
    sheet = np.zeros((H + 2 * pad, W + 2 * pad, 4), np.uint8)
    sheet[pad:pad + H, pad:pad + W, :3] = np.asarray(env.convert("RGB"))
    sheet[pad:pad + H, pad:pad + W, 3] = 255
    return sheet, pad


def _box_entry(poly_sheet: np.ndarray, Hm: np.ndarray, OW: int, OH: int) -> dict:
    p = transform_points(Hm, poly_sheet)
    x0, y0 = np.clip(p.min(0), 0, [OW, OH])
    x1, y1 = np.clip(p.max(0), 0, [OW, OH])
    return {
        "bbox": [int(np.floor(x0)), int(np.floor(y0)), int(np.ceil(x1)), int(np.ceil(y1))],
        "polygon": [[round(float(x), 1), round(float(y), 1)] for x, y in p],
        "visibility": round(visible_fraction(p, OW, OH), 3),
    }


def _forced_effects(reason: str | None, rng, OW: int, est_text_px: float) -> dict:
    """Photographic overrides for illegible samples, scaled to the recipient text size in the photo."""
    k = OW / 1600.0
    t = max(8.0, est_text_px)
    if reason == "heavy_blur":
        if rng.random() < 0.55:
            return {"defocus_radius": max(6 * k, rng.uniform(0.35, 0.5) * t)}
        return {"motion_length": max(25 * k, rng.uniform(1.3, 2.0) * t), "defocus_radius": rng.uniform(0.12, 0.2) * t}
    if reason == "messy_handwriting":   # scrawl photographed slightly out of focus
        return {"defocus_radius": max(1.5 * k, rng.uniform(0.1, 0.15) * t)}
    if reason == "extreme_low_light":
        return {"low_light_gain": rng.uniform(0.15, 0.24), "noise_sigma": rng.uniform(0.05, 0.08),
                "jpeg_quality": int(rng.integers(20, 40)), "defocus_radius": max(2.5 * k, rng.uniform(0.15, 0.22) * t)}
    return {}


def _degraded(applied: list[dict], th: dict, text_px: float) -> list[str]:
    why = []
    p = {a["name"]: a["params"] for a in applied}
    if p.get("defocus_blur", {}).get("radius_px", 0) > th["defocus_radius"]:
        why.append("defocus_blur")
    if p.get("motion_blur", {}).get("length_px", 0) > th["motion_length"]:
        why.append("motion_blur")
    if p.get("noise", {}).get("sigma", 0) > th["noise_sigma"]:
        why.append("noise")
    if p.get("low_light", {}).get("gain", 1) < th["low_light_gain"]:
        why.append("low_light")
    if p.get("jpeg_compression", {}).get("quality", 100) < th["jpeg_quality"]:
        why.append("jpeg_compression")
    if p.get("shadow", {}).get("strength", 0) > th["shadow_strength"]:
        why.append("shadow")
    if text_px < th["min_recipient_text_height_px"]:
        why.append("small_text")
    return why


def generate_sample(index: int, cfg: dict, seed: int, strength: str, out_dir: Path) -> dict:
    ss = np.random.SeedSequence(seed, spawn_key=(index,))
    r_content, r_front, r_back, r_damage, r_aug_f, r_aug_b = (np.random.default_rng(s) for s in ss.spawn(6))
    sample_id = f"{cfg['output'].get('id_prefix', 'mail_')}{index:06d}"
    OW, OH = int(cfg["output"]["width"]), int(cfg["output"]["height"])
    preset = augment_preset(cfg, strength)

    # ---- decide difficulty, then content
    illegible = chance(r_content, float(cfg["illegible_rate"]))
    reason = weighted(r_content, cfg["illegible_reasons"]) if illegible else None
    fk = _faker(int(r_content.integers(2 ** 31)))
    from .content import make_content
    content: MailContent = make_content(cfg, fk, r_content, force_messy=(reason == "messy_handwriting"))
    spec = choose_spec(cfg, content, r_content)

    # ---- flat renders
    front: Rendered = render_front(cfg, content, spec, r_front, messy_recipient=(reason == "messy_handwriting"))
    back: Rendered = render_back(cfg, content, spec, r_back, note_start=len(front.notes))

    # ---- envelope-space damage
    damage: dict = {}
    rbox = front.boxes["recipient"]
    text_px = front.meta.get("recipient_font_px", 30)
    if reason == "water_damage":
        damage = degrade.water_damage(front.image, rbox, r_damage, text_px)
        front.boxes["damage"] = damage["stain_box"]
    elif reason == "smudge":
        damage = degrade.smudge(front.image, rbox, r_damage, text_px)
        front.boxes["damage"] = rbox
    elif reason == "sticker_cover":
        damage = degrade.sticker_cover(front.image, rbox, r_damage, spec.ppi)
        front.boxes["occluder"] = damage["occluder_box"]

    pad = int(0.3 * max(spec.W, spec.H)) if reason == "overlapping_envelope" else 4
    sheet_f, _ = make_sheet(front.image, pad)
    sheet_b, _ = make_sheet(back.image, pad)
    env_quad = rect_poly((pad, pad, pad + spec.W, pad + spec.H))
    polys_f = {k: rect_poly(b) + pad for k, b in front.boxes.items()}
    polys_b = {k: rect_poly(b) + pad for k, b in back.boxes.items()}
    if reason == "overlapping_envelope":
        rb = front.boxes["recipient"]
        damage = degrade.overlapping_envelope(sheet_f, (rb[0] + pad, rb[1] + pad, rb[2] + pad, rb[3] + pad),
                                              tuple(int(v) for v in (pad, pad, pad + spec.W, pad + spec.H)),
                                              r_damage, pick_font(r_damage, "print"))
        polys_f["occluder"] = np.array(damage["occluder_polygon"], np.float64)

    # ---- phone photos
    required_f = [polys_f["recipient"]]
    if "sender" in polys_f and not illegible:
        required_f.append(polys_f["sender"])
    required_b = [polys_b["sender"]] if "sender" in polys_b else []
    # rough on-photo text size (envelope fills ~75% of the frame) to scale forced blur
    est_scale = 0.75 * min(OW / spec.W, OH / spec.H)
    force = _forced_effects(reason, r_aug_f, OW, text_px * est_scale)
    readable = None if illegible else (polys_f["recipient"].mean(0), text_px)
    img_f, H_f, applied_f = photograph(sheet_f, env_quad, preset, r_aug_f, OW, OH, required_f, force=force,
                                       readable_text=readable)
    img_b, H_b, applied_b = photograph(sheet_b, env_quad, preset, r_aug_b, OW, OH, required_b)

    # ---- boxes in final image coordinates
    boxes_f = {k: _box_entry(p, H_f, OW, OH) for k, p in polys_f.items()}
    boxes_b = {k: _box_entry(p, H_b, OW, OH) for k, p in polys_b.items()}
    if "occluder" in polys_f:
        for k, pf in polys_f.items():
            if k in ("occluder", "window", "address_label"):
                continue
            frac = degrade.covered_fraction((pf[0, 0], pf[0, 1], pf[2, 0], pf[2, 1]), polys_f["occluder"])
            if frac > 0 or k == "recipient":
                boxes_f[k]["occluded_fraction"] = round(frac, 3)

    # ---- legibility
    rc = polys_f["recipient"].mean(0)
    rec_text_px = text_px * local_scale(H_f, rc)
    if illegible:
        legibility, degraded_by = "illegible", []
    else:
        degraded_by = _degraded(applied_f, cfg["degraded_thresholds"], rec_text_px)
        legibility = "degraded" if degraded_by else "clear"

    # ---- write images
    q = int(cfg["output"]["jpeg_quality"])
    img_dir = out_dir / "images"
    Image.fromarray(img_f).save(img_dir / f"{sample_id}_front.jpg", quality=q)
    Image.fromarray(img_b).save(img_dir / f"{sample_id}_back.jpg", quality=q)

    label = build_label(sample_id, index, seed, strength, content, spec, front, back, reason, damage, legibility,
                        degraded_by, rec_text_px, applied_f, applied_b, boxes_f, boxes_b, OW, OH)
    (out_dir / "labels" / f"{sample_id}.json").write_text(json.dumps(label, indent=2, ensure_ascii=False))
    return manifest_row(label)


def build_label(sample_id, index, seed, strength, content, spec, front, back, reason, damage, legibility,
                degraded_by, rec_text_px, applied_f, applied_b, boxes_f, boxes_b, OW, OH) -> dict:
    s, r = content.sender, content.recipient
    loc = s.address_location
    shown = loc != "none"
    notes_detail = []
    for side_render, side in ((front, "front"), (back, "back")):
        for note, key in side_render.notes:
            notes_detail.append({"text": note.text, "side": side, "style": note.style, "box": key})
    sender_raw_front = (s.block_lines() + s.extra_lines) if loc in ("front", "both") else []
    return {
        "id": sample_id,
        "generator": {"seed": seed, "index": index, "augment_strength": strength},
        "images": {
            "front": {"file": f"images/{sample_id}_front.jpg", "width": OW, "height": OH},
            "back": {"file": f"images/{sample_id}_back.jpg", "width": OW, "height": OH},
        },
        "sender": {
            "name": s.name if shown else None,
            "organization": s.organization if shown else None,
            "department": s.department if shown else None,
            "address_lines": list(s.address_lines),
            "sender_type": s.sender_type,
            "sender_subtype": s.sender_subtype,
            "address_location": loc,
            "raw_lines_front": sender_raw_front,
            "raw_lines_back": list(content.back_flap_lines),
        },
        "recipient": {
            "name": r.name,
            "canonical_name": r.canonical_name,
            "name_variant": r.name_variant,
            "care_of": r.care_of,
            "address_lines": list(r.address_lines),
            "addressing": r.addressing,
            "raw_lines": r.block_lines(),
        },
        "notes": [n["text"] for n in notes_detail],
        "notes_detail": notes_detail,
        "received_at": content.received_at.isoformat(timespec="seconds"),
        "postmark_date": content.postmark_date.date().isoformat() if content.postmark_date else None,
        "is_handwritten": {
            "sender": bool(s.handwritten) if shown else None,
            "recipient": bool(r.handwritten),
        },
        "legibility": legibility,
        "illegible_reason": reason,
        "degraded_by": degraded_by,
        "recipient_text_px": round(float(rec_text_px), 1),
        "envelope": {
            "size": spec.size, "width_in": spec.width_in, "height_in": spec.height_in, "kind": spec.kind,
            "color": spec.color, "window": spec.window, "address_label": spec.recipient_label,
            "postage": content.postage, "flap": back.meta.get("flap"), "seal": back.meta.get("seal"),
        },
        "damage": {k: v for k, v in damage.items() if k not in ("occluder_polygon",)} or None,
        "augmentations_applied": [{"side": "front", **a} for a in applied_f] + [{"side": "back", **a} for a in applied_b],
        "boxes": {"front": boxes_f, "back": boxes_b},
    }


MANIFEST_FIELDS = ["id", "front_image", "back_image", "label_file", "sender_type", "sender_subtype", "sender_name",
                   "sender_organization", "sender_address_location", "recipient_name", "recipient_canonical_name",
                   "recipient_name_variant", "recipient_care_of", "recipient_addressing", "notes", "received_at",
                   "legibility", "illegible_reason", "handwritten_sender", "handwritten_recipient", "envelope_size",
                   "window", "postage"]


def manifest_row(label: dict) -> dict:
    s, r = label["sender"], label["recipient"]
    return {
        "id": label["id"],
        "front_image": label["images"]["front"]["file"],
        "back_image": label["images"]["back"]["file"],
        "label_file": f"labels/{label['id']}.json",
        "sender_type": s["sender_type"],
        "sender_subtype": s["sender_subtype"] or "",
        "sender_name": s["name"] or "",
        "sender_organization": s["organization"] or "",
        "sender_address_location": s["address_location"],
        "recipient_name": r["name"],
        "recipient_canonical_name": r["canonical_name"] or "",
        "recipient_name_variant": r["name_variant"],
        "recipient_care_of": r["care_of"] or "",
        "recipient_addressing": r["addressing"],
        "notes": " | ".join(label["notes"]),
        "received_at": label["received_at"],
        "legibility": label["legibility"],
        "illegible_reason": label["illegible_reason"] or "",
        "handwritten_sender": "" if label["is_handwritten"]["sender"] is None else int(label["is_handwritten"]["sender"]),
        "handwritten_recipient": int(label["is_handwritten"]["recipient"]),
        "envelope_size": label["envelope"]["size"],
        "window": int(label["envelope"]["window"]),
        "postage": label["envelope"]["postage"],
    }
