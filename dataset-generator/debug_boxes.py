#!/usr/bin/env python3
"""Draw label polygons/boxes on dataset images so labels can be checked by eye.

    python debug_boxes.py --data dataset/ --n 8                 # first 8 samples
    python debug_boxes.py --data dataset/ --ids mail_000003     # specific samples
    python debug_boxes.py --data dataset/ --legibility illegible --n 6

Writes {id}_debug.jpg (front | back side by side, with the key label text underneath)
to <data>/debug/ unless --out is given.
"""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

COLORS = {
    "recipient": (0, 200, 0), "sender": (0, 120, 255), "stamp": (255, 140, 0), "postmark": (200, 120, 0),
    "occluder": (255, 0, 0), "damage": (255, 0, 160), "window": (150, 150, 150), "barcode": (120, 120, 120),
    "logo": (0, 200, 200), "address_label": (90, 160, 90), "sender_extra": (0, 80, 180),
}
NOTE_COLOR = (230, 0, 230)
OTHER = (160, 160, 0)


def _font(size):
    for p in (str(HERE / "fonts" / "Lato-Bold.ttf"), "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_side(img: Image.Image, boxes: dict) -> Image.Image:
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    f = _font(18)
    for key, b in boxes.items():
        col = NOTE_COLOR if key.startswith("note_") else COLORS.get(key, OTHER)
        poly = [tuple(p) for p in b["polygon"]]
        d.polygon(poly, outline=col, width=3)
        x0, y0, x1, y1 = b["bbox"]
        d.rectangle((x0, y0, x1, y1), outline=col + (0,), width=1)
        tag = key
        if b.get("visibility", 1) < 0.999:
            tag += f" vis={b['visibility']:.2f}"
        if "occluded_fraction" in b:
            tag += f" occ={b['occluded_fraction']:.2f}"
        tx, ty = max(0, min(p[0] for p in poly)), max(0, min(p[1] for p in poly) - 22)
        tw = d.textlength(tag, font=f)
        d.rectangle((tx, ty, tx + tw + 6, ty + 21), fill=(0, 0, 0))
        d.text((tx + 3, ty + 1), tag, font=f, fill=col)
    return img


def summary(label: dict) -> list[str]:
    s, r = label["sender"], label["recipient"]
    return [
        f"{label['id']}  legibility={label['legibility']}  reason={label.get('illegible_reason')}  "
        f"degraded_by={label.get('degraded_by')}  envelope={label['envelope']['size']} {label['envelope']['color']}"
        f"{' window' if label['envelope']['window'] else ''}",
        f"SENDER [{s['sender_type']}/{s.get('sender_subtype')}] location={s['address_location']} "
        f"hw={label['is_handwritten']['sender']}: name={s['name']!r} org={s['organization']!r} addr={s['address_lines']}",
        f"RECIPIENT [{r['addressing']}, {r['name_variant']}] hw={label['is_handwritten']['recipient']}: "
        f"name={r['name']!r} (canonical {r['canonical_name']!r}) c/o={r['care_of']!r} addr={r['address_lines']}",
        f"NOTES: {label['notes']}   received_at={label['received_at']}",
        "AUG front: " + ", ".join(a["name"] for a in label["augmentations_applied"] if a["side"] == "front"),
    ]


def render(data: Path, label: dict) -> Image.Image:
    front = draw_side(Image.open(data / label["images"]["front"]["file"]), label["boxes"]["front"])
    back = draw_side(Image.open(data / label["images"]["back"]["file"]), label["boxes"]["back"])
    lines = []
    for ln in summary(label):
        lines += textwrap.wrap(ln, 190) or [""]
    f = _font(20)
    text_h = 28 * len(lines) + 16
    W = front.width + back.width + 20
    canvas = Image.new("RGB", (W, max(front.height, back.height) + text_h), (30, 30, 30))
    canvas.paste(front, (0, 0))
    canvas.paste(back, (front.width + 20, 0))
    d = ImageDraw.Draw(canvas)
    y = max(front.height, back.height) + 8
    for ln in lines:
        d.text((10, y), ln, font=f, fill=(235, 235, 235))
        y += 28
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(HERE / "dataset"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--legibility", choices=["clear", "degraded", "illegible"])
    ap.add_argument("--scale", type=float, default=0.6, help="downscale the debug image")
    args = ap.parse_args()
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "debug"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted((data / "labels").glob("*.json"))
    if args.ids:
        files = [data / "labels" / f"{i}.json" for i in args.ids]
    n = 0
    for fp in files:
        label = json.loads(fp.read_text())
        if args.legibility and label["legibility"] != args.legibility:
            continue
        img = render(data, label)
        if args.scale != 1:
            img = img.resize((int(img.width * args.scale), int(img.height * args.scale)), Image.LANCZOS)
        img.save(out / f"{label['id']}_debug.jpg", quality=88)
        n += 1
        if n >= args.n:
            break
    print(f"wrote {n} debug images to {out}/")


if __name__ == "__main__":
    main()
