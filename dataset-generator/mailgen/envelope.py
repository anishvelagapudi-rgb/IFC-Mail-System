"""Draw the front and back of an envelope and record every element's box.

Coordinates are pixels in the flat (unaugmented) envelope image. Boxes are axis-aligned
rectangles (x0, y0, x1, y1) of the ink actually pasted; augment.py later maps their 4
corners through the photo homography.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .content import MailContent, chance, choice, weighted
from . import noise as fastnoise
from .fonts import get_font, pick_font
from .text import INK_COLORS, TextStyle, render_lines, render_rubber_stamp

# name: (width_in, height_in, kind)
ENVELOPE_SIZES = {
    "#10": (9.5, 4.125, "business"),
    "#6_3/4": (6.5, 3.625, "personal"),
    "A7": (7.25, 5.25, "card"),
    "6x9": (9.0, 6.0, "booklet"),
    "9x12": (12.0, 9.0, "large"),
    "10x13": (13.0, 10.0, "large"),
}

PAPER = {
    "white": (246, 246, 242), "offwhite": (240, 237, 227), "cream": (242, 233, 208),
    "gray_recycled": (226, 224, 216), "light_blue": (216, 228, 240), "pink": (246, 223, 226),
    "light_green": (222, 238, 220), "manila": (222, 194, 140), "kraft": (186, 146, 100),
}

Rect = tuple[int, int, int, int]


@dataclass
class EnvelopeSpec:
    size: str
    width_in: float
    height_in: float
    kind: str
    color: str
    window: bool
    recipient_label: bool
    ppi: float
    W: int
    H: int
    flap: str


@dataclass
class Rendered:
    image: Image.Image
    boxes: dict[str, Rect] = field(default_factory=dict)
    notes: list = field(default_factory=list)          # [(Note, box_key)] actually drawn
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- spec


def choose_spec(cfg: dict, content: MailContent, rng) -> EnvelopeSpec:
    st = content.sender.sender_type
    if st == "personal":
        size = weighted(rng, {"#6_3/4": 0.35, "A7": 0.35, "#10": 0.25, "6x9": 0.05})
        color = weighted(rng, {"white": 0.35, "cream": 0.2, "offwhite": 0.1, "light_blue": 0.13, "pink": 0.12,
                               "light_green": 0.05, "kraft": 0.05})
    else:
        size = weighted(rng, {"#10": 0.72, "6x9": 0.1, "9x12": 0.12, "10x13": 0.06})
        color = weighted(rng, {"white": 0.6, "offwhite": 0.2, "gray_recycled": 0.15, "light_blue": 0.05})
    w, h, kind = ENVELOPE_SIZES[size]
    if kind == "large" or (kind == "booklet" and chance(rng, 0.5)):
        color = weighted(rng, {"manila": 0.6, "kraft": 0.15, "white": 0.25})
    window = st != "personal" and kind in ("business", "booklet") and chance(rng, cfg["envelope"]["window_rate_business"])
    if content.recipient.handwritten:
        window = False
    label = kind == "large" and not content.recipient.handwritten and chance(rng, cfg["envelope"]["recipient_label_rate_large"])
    ppi = cfg["render"]["long_side_px"] / max(w, h)
    flap = "clasp" if kind == "large" else choice(rng, ["pointed", "straight", "curved"] if kind != "booklet" else ["straight"])
    return EnvelopeSpec(size, w, h, kind, color, window, label, ppi, int(round(w * ppi)), int(round(h * ppi)), flap)


# --------------------------------------------------------------------------- paper


def paper_texture(spec: EnvelopeSpec, rng) -> Image.Image:
    base = np.array(PAPER[spec.color], dtype=np.float32) * (1 + rng.normal(0, 0.01, 3)).astype(np.float32)
    H, W = spec.H, spec.W
    kraft = spec.color in ("manila", "kraft")
    # single-channel luminance modulation: low-frequency mottling + fine grain (+ fibers for kraft)
    small = rng.normal(0, 1, (max(2, H // 60), max(2, W // 60))).astype(np.float32)
    mott = cv2.resize(cv2.GaussianBlur(small, (0, 0), 0.6), (W, H), interpolation=cv2.INTER_CUBIC)
    lum = 1 + mott * (0.008 if kraft else 0.005)
    lum += fastnoise.gaussian(rng, H, W, 1)[..., 0] * ((3.5 if kraft else 1.5) / float(base.mean()))
    if kraft:
        n = int(W * H / 2500)
        fib = np.zeros((H, W), np.float32)
        xs, ys = rng.integers(0, W, n), rng.integers(0, H, n)
        ang = rng.uniform(0, np.pi, n)
        ln = rng.uniform(4, 14, n)
        x2, y2 = xs + ln * np.cos(ang), ys + ln * np.sin(ang)
        cv2.polylines(fib, [np.array([[x0, y0], [x1, y1]], np.int32).reshape(-1, 1, 2)
                            for x0, y0, x1, y1 in zip(xs, ys, x2, y2)], False, 1.0, 1)
        lum -= fib * (rng.uniform(8, 18) / float(base.mean()))
    img = cv2.merge([lum * base[0], lum * base[1], lum * base[2]])
    return Image.fromarray(cv2.convertScaleAbs(img), "RGB")


# --------------------------------------------------------------------------- layout helper


class Layout:
    def __init__(self, W: int, H: int, margin: int):
        self.W, self.H, self.margin = W, H, margin
        self.occupied: list[Rect] = []

    def free(self, r: Rect, gap: int = 6) -> bool:
        x0, y0, x1, y1 = r
        if x0 < self.margin * 0.5 or y0 < self.margin * 0.5 or x1 > self.W - self.margin * 0.5 or y1 > self.H - self.margin * 0.5:
            return False
        for a in self.occupied:
            if not (x1 + gap <= a[0] or a[2] + gap <= x0 or y1 + gap <= a[1] or a[3] + gap <= y0):
                return False
        return True

    def add(self, r: Rect):
        self.occupied.append(r)


def paste(img: Image.Image, tile: Image.Image, x: int, y: int) -> Rect:
    x, y = int(round(x)), int(round(y))
    img.paste(tile, (x, y), tile)
    return (x, y, x + tile.width, y + tile.height)


def clamp_xy(x, y, tile, W, H, m):
    x = min(max(m, x), W - m - tile.width)
    y = min(max(m, y), H - m - tile.height)
    return x, y


# --------------------------------------------------------------------------- styles


def hand_style(rng, ppi: float, em_in: tuple[float, float], messy: bool = False, color=None) -> TextStyle:
    font = pick_font(rng, "messy" if messy else "handwriting")
    if color is None:
        color = INK_COLORS[weighted(rng, {"blue": 0.45, "black": 0.35, "darkblue": 0.12, "pencil": 0.08})]
    if messy:
        color = INK_COLORS[weighted(rng, {"pencil": 0.5, "blue": 0.25, "black": 0.25})]
    if messy:
        return TextStyle(font=font, size=int(ppi * rng.uniform(*em_in)), color=color, handwritten=True,
                         jitter=rng.uniform(3.5, 5.0), line_spacing=rng.uniform(0.6, 0.8),
                         slant_deg=rng.normal(0, 7), alpha=rng.uniform(0.25, 0.45), bold=0,
                         char_level=True, squeeze=rng.uniform(0.7, 0.85))
    return TextStyle(font=font, size=int(ppi * rng.uniform(*em_in)), color=color, handwritten=True,
                     jitter=rng.uniform(0.5, 1.4), line_spacing=rng.uniform(1.0, 1.35),
                     slant_deg=rng.normal(0, 2.5), alpha=rng.uniform(0.85, 1.0),
                     bold=int(rng.random() < 0.25), char_level=rng.random() < 0.3)


def print_style(rng, ppi: float, em_in: tuple[float, float], mono: bool | None = None, color=None) -> TextStyle:
    if mono is None:
        mono = rng.random() < 0.4
    font = pick_font(rng, "mono" if mono else "print")
    color = color or INK_COLORS[weighted(rng, {"black": 0.85, "gray": 0.15})]
    typewriter = mono and font.endswith("CourierPrime-Regular.ttf") and rng.random() < 0.5
    return TextStyle(font=font, size=int(ppi * rng.uniform(*em_in)), color=color,
                     line_spacing=rng.uniform(1.05, 1.25), char_level=typewriter)


# --------------------------------------------------------------------------- front elements


def draw_logo(rng, size: int, color) -> Image.Image:
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    kind = choice(rng, ["seal", "square", "triangle", "rings"])
    c = color + (255,)
    s = size
    if kind == "seal":
        d.ellipse((2, 2, s - 3, s - 3), outline=c, width=max(2, s // 16))
        d.ellipse((s * 0.18, s * 0.18, s * 0.82, s * 0.82), outline=c, width=max(1, s // 30))
        for k in range(10):
            a = 2 * np.pi * k / 10
            x, y = s / 2 + 0.41 * s * np.cos(a), s / 2 + 0.41 * s * np.sin(a)
            d.ellipse((x - s * 0.025, y - s * 0.025, x + s * 0.025, y + s * 0.025), fill=c)
        d.polygon([(s * 0.5, s * 0.3), (s * 0.68, s * 0.66), (s * 0.32, s * 0.66)], fill=c)
    elif kind == "square":
        d.rounded_rectangle((2, 2, s - 3, s - 3), radius=s // 6, fill=c)
        d.rectangle((s * 0.25, s * 0.25, s * 0.5, s * 0.75), fill=(255, 255, 255, 255))
        d.rectangle((s * 0.55, s * 0.25, s * 0.75, s * 0.5), fill=(255, 255, 255, 255))
    elif kind == "triangle":
        d.polygon([(s * 0.5, 2), (s - 3, s - 3), (2, s - 3)], fill=c)
        d.polygon([(s * 0.5, s * 0.4), (s * 0.7, s * 0.8), (s * 0.3, s * 0.8)], fill=(255, 255, 255, 255))
    else:
        for k in range(3):
            o = k * s * 0.16
            d.ellipse((o + 2, o + 2, s - o - 3, s - o - 3), outline=c, width=max(2, s // 14))
    return tile


def draw_stamp(rng, ppi: float) -> Image.Image:
    """A fictional postage stamp with perforated edges and procedural art."""
    w, h = int(ppi * rng.uniform(0.8, 0.95)), int(ppi * rng.uniform(0.95, 1.1))
    if rng.random() < 0.3:
        w, h = h, w
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rectangle((0, 0, w - 1, h - 1), fill=(250, 250, 246, 255))
    r = max(2, int(ppi * 0.025))
    step = r * 3
    for x in range(step // 2, w, step):
        d.ellipse((x - r, -r, x + r, r), fill=(0, 0, 0, 0))
        d.ellipse((x - r, h - r, x + r, h + r), fill=(0, 0, 0, 0))
    for y in range(step // 2, h, step):
        d.ellipse((-r, y - r, r, y + r), fill=(0, 0, 0, 0))
        d.ellipse((w - r, y - r, w + r, y + r), fill=(0, 0, 0, 0))
    m = int(ppi * 0.07)
    ix0, iy0, ix1, iy1 = m, m, w - m, h - m
    art = choice(rng, ["stripes", "flower", "landscape", "geo"])
    pal = [tuple(int(v) for v in rng.integers(30, 230, 3)) for _ in range(4)]
    if art == "stripes":
        n = int(rng.integers(5, 10))
        for k in range(n):
            y0 = iy0 + (iy1 - iy0) * k / n
            d.rectangle((ix0, y0, ix1, y0 + (iy1 - iy0) / n), fill=pal[k % 2])
        d.rectangle((ix0, iy0, ix0 + (ix1 - ix0) * 0.45, iy0 + (iy1 - iy0) * 0.45), fill=pal[2])
    elif art == "flower":
        d.rectangle((ix0, iy0, ix1, iy1), fill=pal[0])
        cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
        pr = (ix1 - ix0) * 0.18
        for k in range(6):
            a = 2 * np.pi * k / 6
            d.ellipse((cx + 1.1 * pr * np.cos(a) - pr, cy + 1.1 * pr * np.sin(a) - pr,
                       cx + 1.1 * pr * np.cos(a) + pr, cy + 1.1 * pr * np.sin(a) + pr), fill=pal[1])
        d.ellipse((cx - pr * 0.7, cy - pr * 0.7, cx + pr * 0.7, cy + pr * 0.7), fill=pal[2])
    elif art == "landscape":
        for k in range(iy1 - iy0):
            t = k / max(1, iy1 - iy0)
            col = tuple(int(pal[0][c] * (1 - t) + 240 * t) for c in range(3))
            d.line((ix0, iy0 + k, ix1, iy0 + k), fill=col)
        d.polygon([(ix0, iy1), (ix0, iy0 + (iy1 - iy0) * 0.6), ((ix0 + ix1) * 0.45, iy0 + (iy1 - iy0) * 0.35),
                   (ix1, iy0 + (iy1 - iy0) * 0.7), (ix1, iy1)], fill=pal[1])
    else:
        d.rectangle((ix0, iy0, ix1, iy1), fill=pal[0])
        for _ in range(5):
            x, y = rng.uniform(ix0, ix1), rng.uniform(iy0, iy1)
            rr = rng.uniform(0.08, 0.25) * (ix1 - ix0)
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=pal[int(rng.integers(1, 4))])
    tile_crop = tile.crop((ix0, iy0, ix1, iy1))
    tile.paste(tile_crop, (ix0, iy0))
    font = get_font(pick_font(rng, "print_bold"), int(ppi * 0.13))
    d.text((ix0 + 3, iy1 - 3), "USA", font=font, fill=(255, 255, 255, 255), anchor="lb",
           stroke_width=1, stroke_fill=(30, 30, 30, 255))
    return tile


def draw_meter(rng, ppi: float, content: MailContent) -> Image.Image:
    color = (200, 30, 50) if rng.random() < 0.45 else (30, 30, 35)
    w, h = int(ppi * rng.uniform(1.5, 1.9)), int(ppi * rng.uniform(0.7, 0.85))
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    c = color + (255,)
    lw = max(1, int(ppi * 0.012))
    font = get_font(pick_font(rng, "print_bold"), int(ppi * 0.09))
    big = get_font(pick_font(rng, "print_bold"), int(ppi * 0.17))
    d.rectangle((0, 0, w - 1, h - 1), outline=c, width=lw)
    d.text((w * 0.06, h * 0.08), "US POSTAGE", font=font, fill=c)
    cents = int(rng.integers(55, 90))
    d.text((w * 0.06, h * 0.3), f"$000.{cents:02d}", font=big, fill=c)
    date = content.postmark_date.strftime("%m/%d/%Y") if content.postmark_date else ""
    zipc = (content.sender.address_lines[-1].split()[-1][:5] if content.sender.address_lines else "27701")
    d.text((w * 0.06, h * 0.62), f"{date}  ZIP {zipc}", font=font, fill=c)
    d.text((w * 0.06, h * 0.8), f"{int(rng.integers(10, 99)):02d}M{int(rng.integers(1e7, 1e8 - 1))}", font=font, fill=c)
    # 2-D indicia barcode block
    gx0, gy0, cell = int(w * 0.68), int(h * 0.12), max(2, int(ppi * 0.018))
    for i in range(14):
        for j in range(14):
            if rng.random() < 0.5:
                d.rectangle((gx0 + i * cell, gy0 + j * cell, gx0 + (i + 1) * cell - 1, gy0 + (j + 1) * cell - 1), fill=c)
    return tile


def draw_permit(rng, ppi: float, content: MailContent) -> Image.Image:
    st = content.sender.sender_type
    first = "PRESORTED" if rng.random() < 0.6 else "PRSRT"
    second = "FIRST-CLASS MAIL" if st != "junk" or rng.random() < 0.3 else "STANDARD"
    city_line = content.sender.address_lines[-1] if content.sender.address_lines else "RALEIGH NC"
    city = city_line.rsplit(" ", 1)[0].upper().replace(",", "")
    lines = [first, second, "U.S. POSTAGE PAID", city[:22], f"PERMIT NO. {int(rng.integers(10, 9999))}"]
    font = get_font(pick_font(rng, "print_bold"), int(ppi * 0.085))
    lh = int(ppi * 0.115)
    w = int(max(font.getlength(s) for s in lines) + ppi * 0.16)
    h = lh * len(lines) + int(ppi * 0.12)
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    c = (30, 30, 35, 255)
    d.rectangle((0, 0, w - 1, h - 1), outline=c, width=max(1, int(ppi * 0.01)))
    for k, s in enumerate(lines):
        d.text((w / 2, ppi * 0.06 + k * lh), s, font=font, fill=c, anchor="ma")
    return tile


def draw_postmark(rng, ppi: float, content: MailContent, stamp_h: int) -> Image.Image:
    """Circular date stamp + wavy cancellation lines (drawn to the left of / over the stamp)."""
    r = int(ppi * rng.uniform(0.42, 0.5))
    wave_w = int(ppi * rng.uniform(1.4, 2.0))
    w, h = 2 * r + wave_w + 8, max(2 * r, stamp_h) + 8
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    ink = (35, 35, 45) if rng.random() < 0.7 else (40, 50, 110)
    c = ink + (255,)
    cx, cy = r + 4, h // 2
    lw = max(1, int(ppi * 0.012))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=lw)
    city = "PROCESSING CTR"
    if content.sender.address_lines:
        parts = content.sender.address_lines[-1].replace(",", "").split()
        if len(parts) >= 3:
            city = (" ".join(parts[:-2]) + " " + parts[-2]).upper()[:16]
    f1 = get_font(pick_font(rng, "print_bold"), int(ppi * 0.085))
    f2 = get_font(pick_font(rng, "print_bold"), int(ppi * 0.1))
    d.text((cx, cy - r * 0.45), city, font=f1, fill=c, anchor="mm")
    if content.postmark_date:
        d.text((cx, cy), content.postmark_date.strftime("%b %d %Y").upper(), font=f2, fill=c, anchor="mm")
    d.text((cx, cy + r * 0.45), "PM " + str(int(rng.integers(1, 12))) + " L", font=f1, fill=c, anchor="mm")
    x0 = cx + r + 6
    amp, per = ppi * 0.05, ppi * rng.uniform(0.25, 0.35)
    for k in range(int(rng.integers(4, 7))):
        yb = cy - r + (k + 0.5) * (2 * r) / 6
        pts = [(x0 + t, yb + amp * np.sin(2 * np.pi * t / per)) for t in range(0, wave_w, 3)]
        d.line(pts, fill=c, width=lw)
    a = np.asarray(tile.getchannel("A"), dtype=np.float32)
    keep = rng.random(a.shape) > rng.uniform(0.15, 0.4)
    a = a * keep * rng.uniform(0.55, 0.85)
    tile.putalpha(Image.fromarray(a.astype(np.uint8)))
    return tile.rotate(rng.uniform(-6, 6), resample=Image.BICUBIC, expand=True)


def draw_imb(rng, ppi: float) -> Image.Image:
    """Intelligent-Mail-style 65-bar, 4-state barcode (random data)."""
    bar_w, pitch = max(1, int(ppi * 0.02)), max(2, int(ppi * 0.042))
    full, half = int(ppi * 0.145), int(ppi * 0.08)
    track = int(ppi * 0.045)
    w, h = 65 * pitch, full
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    for i in range(65):
        s = int(rng.integers(4))
        mid = h / 2
        if s == 0:
            y0, y1 = 0, h
        elif s == 1:
            y0, y1 = 0, mid + track / 2
        elif s == 2:
            y0, y1 = mid - track / 2, h
        else:
            y0, y1 = mid - track / 2, mid + track / 2
        d.rectangle((i * pitch, y0, i * pitch + bar_w, y1), fill=(20, 20, 25, 255))
    return tile


# --------------------------------------------------------------------------- front


def render_front(cfg: dict, content: MailContent, spec: EnvelopeSpec, rng, messy_recipient: bool = False) -> Rendered:
    W, H, ppi = spec.W, spec.H, spec.ppi
    img = paper_texture(spec, rng)
    out = Rendered(img)
    m = int(ppi * rng.uniform(0.22, 0.35))
    lay = Layout(W, H, m)
    s, rcp = content.sender, content.recipient
    large = spec.kind == "large"

    # ---- window
    window = None
    if spec.window:
        if spec.kind == "business":
            wx0, ww, wh = 0.875 * ppi, 4.5 * ppi, 1.125 * ppi
            wy0 = H - 0.625 * ppi - wh
        else:
            wx0, ww, wh = 0.9 * ppi, 4.6 * ppi, 1.3 * ppi
            wy0 = H * 0.42
        window = tuple(int(v) for v in (wx0, wy0, wx0 + ww, wy0 + wh))
        d = ImageDraw.Draw(img)
        inner = (250, 250, 248) if spec.color != "white" else (253, 253, 252)
        d.rounded_rectangle(window, radius=int(ppi * 0.06), fill=inner)
        out.boxes["window"] = window
        lay.add(window)          # keep notes / stamps-like marks off the window film

    # ---- postage (top-right)
    if content.postage == "stamp":
        stamps = [draw_stamp(rng, ppi) for _ in range(2 if large and chance(rng, 0.5) else 1)]
        gap = int(ppi * 0.06)
        sw = sum(t.width for t in stamps) + gap * (len(stamps) - 1)
        sh = max(t.height for t in stamps)
        x, y = W - m - sw + int(rng.normal(0, ppi * 0.03)), m + int(rng.normal(0, ppi * 0.03))
        x, y = clamp_xy(x, y, Image.new("L", (sw, sh)), W, H, int(m * 0.5))
        tiles = []
        for t in stamps:
            t = t.rotate(rng.normal(0, 2.0), resample=Image.BICUBIC, expand=True)
            tiles.append(paste(img, t, x, y))
            x += t.width + gap
        stamp_box = (min(b[0] for b in tiles), min(b[1] for b in tiles), max(b[2] for b in tiles), max(b[3] for b in tiles))
    else:
        t = draw_meter(rng, ppi, content) if content.postage == "meter" else draw_permit(rng, ppi, content)
        x, y = W - m - t.width, m
        stamp_box = paste(img, t, x, y)
    out.boxes["stamp"] = stamp_box
    lay.add(stamp_box)

    if content.postage == "stamp" and content.postmark_date and chance(rng, 0.85):
        pm = draw_postmark(rng, ppi, content, stamp_box[3] - stamp_box[1])
        px = stamp_box[0] - int(pm.width * rng.uniform(0.35, 0.6))
        py = stamp_box[1] + (stamp_box[3] - stamp_box[1]) // 2 - pm.height // 2 + int(rng.normal(0, ppi * 0.04))
        px, py = clamp_xy(px, py, pm, W, H, int(m * 0.3))
        b = paste(img, pm, px, py)
        out.boxes["postmark"] = b
        lay.add((b[0], b[1], stamp_box[0], b[3]))

    # ---- sender block (top-left)
    if s.address_location in ("front", "both"):
        lines = s.block_lines()
        if s.handwritten:
            st = hand_style(rng, ppi, (0.16, 0.24))
            tile = render_lines(lines, st, rng)
            out.meta["sender_font"] = st.font
        else:
            st = print_style(rng, ppi, (0.10, 0.13) if not large else (0.12, 0.15))
            tile = render_lines(lines, st, rng)
            out.meta["sender_font"] = st.font
            if s.organization and chance(rng, 0.55):
                logo_color = INK_COLORS[choice(rng, ["darkblue", "black", "red", "purple", "gray"])]
                logo = draw_logo(rng, int(tile.height * rng.uniform(0.7, 1.0)), logo_color)
                lb = paste(img, logo, m, m)
                out.boxes["logo"] = lb
                lay.add(lb)
                x_text = lb[2] + int(ppi * 0.08)
            else:
                x_text = m
        maxw = W * 0.48
        if tile.width > maxw:
            tile = tile.resize((int(maxw), int(tile.height * maxw / tile.width)), Image.LANCZOS)
        x0 = m if s.handwritten else x_text
        y0 = m + (int(rng.normal(0, ppi * 0.04)) if s.handwritten else 0)
        x0, y0 = clamp_xy(x0, y0, tile, W, H, int(m * 0.5))
        b = paste(img, tile, x0, y0)
        out.boxes["sender"] = b
        lay.add(b)
        if s.extra_lines:
            et = render_lines(s.extra_lines, print_style(rng, ppi, (0.075, 0.09), mono=False), rng)
            eb = paste(img, et, b[0], b[3] + int(ppi * 0.05))
            out.boxes["sender_extra"] = eb
            lay.add(eb)

    # ---- recipient block
    lines = rcp.block_lines()
    if rcp.handwritten:
        em = (0.22, 0.32) if not large else (0.3, 0.42)
        st = hand_style(rng, ppi, em, messy=messy_recipient)
        if messy_recipient:
            st.size = int(st.size * rng.uniform(0.7, 0.9))
    else:
        em = (0.14, 0.18) if not large else (0.17, 0.23)
        st = print_style(rng, ppi, em)
    out.meta["recipient_font"] = st.font
    out.meta["recipient_font_px"] = st.size
    limit_w = (window[2] - window[0] - ppi * 0.3) if window else W * (0.62 if not rcp.handwritten else 0.78)
    limit_h = (window[3] - window[1] - ppi * 0.12) if window else H * 0.5
    for _ in range(12):
        tile = render_lines(lines, st, rng)
        if tile.width <= limit_w and tile.height <= limit_h:
            break
        st.size = int(st.size * 0.9)
        out.meta["recipient_font_px"] = st.size

    if window:
        rx = window[0] + int(ppi * rng.uniform(0.12, 0.3))
        ry = window[1] + (window[3] - window[1] - tile.height) // 2 + int(rng.normal(0, ppi * 0.03))
        ry = min(max(ry, window[1] + 2), window[3] - tile.height - 2)
        rx = min(rx, window[2] - tile.width - 2)
    elif rcp.handwritten:
        rx = (W - tile.width) / 2 + rng.normal(0, W * 0.04)
        ry = H * rng.uniform(0.36, 0.5)
    else:
        rx = W * rng.uniform(0.33, 0.46)
        ry = H * rng.uniform(0.42, 0.52) if not large else H * rng.uniform(0.38, 0.5)
    # keep clear of the top band (sender / stamp) and inside the envelope
    top_band = max([b[3] for k, b in out.boxes.items() if k in ("sender", "sender_extra", "stamp", "logo")] + [0])
    if not window:
        ry = max(ry, top_band + ppi * 0.15)
        rx, ry = clamp_xy(rx, ry, tile, W, H, m)

    if spec.recipient_label and not window:
        pad = int(ppi * 0.12)
        lab = Image.new("RGBA", (tile.width + 2 * pad, tile.height + 2 * pad), (252, 252, 250, 255))
        ImageDraw.Draw(lab).rectangle((0, 0, lab.width - 1, lab.height - 1), outline=(215, 215, 210, 255))
        lx, ly = clamp_xy(rx - pad, ry - pad, lab, W, H, int(m * 0.5))
        out.boxes["address_label"] = paste(img, lab, lx, ly)
        rx, ry = lx + pad, ly + pad
    b = paste(img, tile, rx, ry)
    out.boxes["recipient"] = b
    if window:
        # glassine film over the window: slight haze + visible edge
        film = Image.new("RGBA", img.size, (0, 0, 0, 0))
        fd = ImageDraw.Draw(film)
        fd.rounded_rectangle(window, radius=int(ppi * 0.06), fill=(225, 228, 232, int(rng.uniform(25, 55))),
                             outline=(170, 170, 175, 160), width=max(1, int(ppi * 0.008)))
        sx = window[0] + (window[2] - window[0]) * rng.uniform(0.1, 0.7)
        fd.polygon([(sx, window[1]), (sx + ppi * 0.35, window[1]), (sx + ppi * 0.15, window[3]),
                    (sx - ppi * 0.2, window[3])], fill=(255, 255, 255, int(rng.uniform(15, 40))))
        img.alpha_composite(film) if img.mode == "RGBA" else img.paste(film, (0, 0), film)
    lay.add(out.boxes.get("address_label", b))

    # ---- IMb barcode
    if not rcp.handwritten and content.sender.sender_type != "personal" and rcp.address_lines and chance(rng, 0.55):
        bc = draw_imb(rng, ppi)
        if window:
            bx, by = b[0], b[3] + int(ppi * 0.03)
            if by + bc.height > window[3] - 2:
                bx, by = b[0], max(window[1] + 2, b[1] - bc.height - int(ppi * 0.03))
                if by + bc.height >= b[1]:
                    bc = None
        else:
            bx, by = W - m - bc.width, H - int(ppi * 0.12) - bc.height
        if bc is not None:
            r = (bx, by, bx + bc.width, by + bc.height)
            if window or lay.free(r, gap=2):
                out.boxes["barcode"] = paste(img, bc, bx, by)
                lay.add(out.boxes["barcode"])

    # ---- notes
    k = 0
    for note in [n for n in content.notes if n.side == "front"]:
        placed = place_note(img, lay, note, out, spec, rng)
        if placed is not None:
            key = f"note_{k}"
            out.boxes[key] = placed
            out.notes.append((note, key))
            k += 1
    out.meta["front_margin"] = m
    return out


def note_tile(note, ppi, rng, shrink=1.0):
    if note.style == "printed":
        bold = rng.random() < 0.7
        font = pick_font(rng, "print_bold" if bold else "print")
        color = INK_COLORS["black"] if rng.random() < 0.7 else INK_COLORS[choice(rng, ["red", "darkblue"])]
        st = TextStyle(font=font, size=int(ppi * rng.uniform(0.1, 0.16) * shrink), color=color)
        return render_lines([note.text], st, rng)
    if note.style == "rubber_stamp":
        color = INK_COLORS["red"] if rng.random() < 0.75 else INK_COLORS["purple"]
        return render_rubber_stamp(note.text, pick_font(rng, "print_bold"), int(ppi * rng.uniform(0.17, 0.26) * shrink),
                                   color, rng)
    st = hand_style(rng, ppi, (0.17 * shrink, 0.26 * shrink))
    st.slant_deg = rng.normal(0, 7)
    return render_lines([note.text], st, rng)


def place_note(img, lay: Layout, note, out: Rendered, spec, rng):
    W, H, ppi, m = spec.W, spec.H, spec.ppi, lay.margin
    for attempt in range(40):
        shrink = 1.0 if attempt < 20 else 0.75
        if attempt % 10 == 0:
            tile = note_tile(note, ppi, rng, shrink)
        zone = note.zone if attempt < 25 else "anywhere"
        sb = out.boxes.get("sender_extra") or out.boxes.get("sender")
        rb = out.boxes["recipient"]
        if zone == "below_return" and sb:
            x, y = sb[0] + rng.normal(0, ppi * 0.03), sb[3] + ppi * rng.uniform(0.08, 0.25)
        elif zone == "above_recipient":
            x, y = rb[0] + rng.normal(0, ppi * 0.1), rb[1] - tile.height - ppi * rng.uniform(0.08, 0.25)
        elif zone == "lower_left":
            x, y = m + rng.uniform(0, W * 0.15), H - m - tile.height - rng.uniform(0, H * 0.12)
        else:
            x, y = rng.uniform(m, W - m - tile.width), rng.uniform(m, H - m - tile.height)
        r = (int(x), int(y), int(x) + tile.width, int(y) + tile.height)
        if lay.free(r, gap=int(ppi * 0.08)):
            b = paste(img, tile, x, y)
            lay.add(b)
            return b
    return None


# --------------------------------------------------------------------------- back


def render_back(cfg: dict, content: MailContent, spec: EnvelopeSpec, rng, note_start: int = 0) -> Rendered:
    W, H, ppi = spec.W, spec.H, spec.ppi
    img = paper_texture(spec, rng)
    out = Rendered(img)
    d = ImageDraw.Draw(img, "RGBA")
    base = np.array(PAPER[spec.color])
    edge = tuple(int(v) for v in base * 0.78) + (255,)
    shade = tuple(int(v) for v in base * 0.93) + (255,)
    lw = max(2, int(ppi * 0.012))

    # side seams (diagonals from bottom corners)
    seam_y = H * rng.uniform(0.45, 0.6)
    if spec.flap != "clasp":
        d.line([(0, H), (W * 0.42, seam_y)], fill=edge, width=lw)
        d.line([(W, H), (W * 0.58, seam_y)], fill=edge, width=lw)
    # flap
    if spec.flap == "pointed":
        tip = H * rng.uniform(0.55, 0.68)
        flap_poly = [(0, 0), (W, 0), (W, H * 0.12), (W / 2, tip), (0, H * 0.12)]
        flap_region = (int(W * 0.3), int(H * 0.08), int(W * 0.7), int(tip * 0.85))
    elif spec.flap == "curved":
        tip = H * rng.uniform(0.45, 0.55)
        pts = [(W * t, H * 0.1 + (tip - H * 0.1) * np.sin(np.pi * t)) for t in np.linspace(0, 1, 40)]
        flap_poly = [(0, 0), (W, 0)] + pts[::-1]
        flap_region = (int(W * 0.25), int(H * 0.06), int(W * 0.75), int(tip * 0.85))
    elif spec.flap == "straight":
        tip = H * rng.uniform(0.3, 0.4)
        flap_poly = [(0, 0), (W, 0), (W, tip), (0, tip)]
        flap_region = (int(W * 0.15), int(H * 0.04), int(W * 0.85), int(tip * 0.92))
    else:  # clasp (large envelope, flap at top)
        tip = H * rng.uniform(0.18, 0.24)
        flap_poly = [(0, 0), (W, 0), (W * 0.93, tip), (W * 0.07, tip)]
        flap_region = (int(W * 0.12), int(H * 0.02), int(W * 0.88), int(tip * 0.9))
    d.polygon(flap_poly, fill=shade)
    d.line(flap_poly[2:] + ([flap_poly[2]] if spec.flap == "straight" else []), fill=edge, width=lw)
    # soft shadow under the flap edge
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).line(flap_poly[2:], fill=90, width=lw * 4)
    sh = sh.filter(ImageFilter.GaussianBlur(ppi * 0.02))
    arr = np.asarray(img, dtype=np.float32) * (1 - np.asarray(sh, dtype=np.float32)[..., None] / 255.0 * 0.25)
    img.paste(Image.fromarray(arr.astype(np.uint8)))
    d = ImageDraw.Draw(img, "RGBA")
    out.meta["flap"] = spec.flap

    if spec.flap == "clasp":
        cx, cy = W / 2, tip + ppi * 0.35
        brass = (184, 150, 70, 255)
        d.ellipse((cx - ppi * 0.07, cy - ppi * 0.07, cx + ppi * 0.07, cy + ppi * 0.07), fill=brass)
        d.polygon([(cx - ppi * 0.35, cy - ppi * 0.04), (cx, cy - ppi * 0.02), (cx, cy + ppi * 0.02),
                   (cx - ppi * 0.35, cy + ppi * 0.04)], fill=brass)
        d.polygon([(cx + ppi * 0.35, cy - ppi * 0.04), (cx, cy - ppi * 0.02), (cx, cy + ppi * 0.02),
                   (cx + ppi * 0.35, cy + ppi * 0.04)], fill=brass)
        out.boxes["clasp"] = (int(cx - ppi * 0.36), int(cy - ppi * 0.08), int(cx + ppi * 0.36), int(cy + ppi * 0.08))

    lay = Layout(W, H, int(ppi * 0.15))
    for k in ("clasp",):
        if k in out.boxes:
            lay.add(out.boxes[k])

    # seal
    seal = weighted(rng, {"none": 0.75, "tape": 0.15, "sticker": 0.1 if content.sender.sender_type == "personal" else 0.0})
    out.meta["seal"] = seal
    if seal == "tape":
        tw, th = int(ppi * rng.uniform(1.2, 2.0)), int(ppi * rng.uniform(0.6, 0.75))
        tape = Image.new("RGBA", (tw, th), (235, 235, 225, 70))
        ImageDraw.Draw(tape).line([(0, 3), (tw, 3)], fill=(255, 255, 255, 120), width=2)
        tape = tape.rotate(rng.uniform(-100, -80) if rng.random() < 0.5 else rng.uniform(-10, 10), expand=True)
        tx, ty = W / 2 - tape.width / 2, min(tip, H * 0.6) - tape.height / 2
        out.boxes["seal"] = paste(img, tape, tx, ty)
    elif seal == "sticker":
        r = int(ppi * rng.uniform(0.22, 0.32))
        st = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
        col = tuple(int(v) for v in rng.integers(120, 240, 3)) + (255,)
        ImageDraw.Draw(st).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=col)
        sx, sy = W / 2 - r, min(tip, H * 0.62) - r
        out.boxes["seal"] = paste(img, st, sx, sy)
    if "seal" in out.boxes:
        lay.add(out.boxes["seal"])

    # return address on the flap
    if content.back_flap_lines:
        if content.back_flap_handwritten:
            st = hand_style(rng, ppi, (0.14, 0.2))
        else:
            st = print_style(rng, ppi, (0.08, 0.11), mono=False)
            st.align = "center"
        fx0, fy0, fx1, fy1 = flap_region
        for _ in range(10):
            tile = render_lines(content.back_flap_lines, st, rng)
            if tile.width <= fx1 - fx0 and tile.height <= fy1 - fy0:
                break
            st.size = int(st.size * 0.88)
        x = (fx0 + fx1 - tile.width) / 2 + rng.normal(0, ppi * 0.05)
        y = fy0 + (fy1 - fy0 - tile.height) * rng.uniform(0.1, 0.5)
        x, y = clamp_xy(x, y, tile, W, H, 4)
        r = (int(x), int(y), int(x) + tile.width, int(y) + tile.height)
        if not lay.free(r, gap=0) and "seal" in out.boxes:
            # move the seal out of the way rather than drop the address
            out.boxes.pop("seal")
        out.boxes["sender"] = paste(img, tile, x, y)
        lay.add(out.boxes["sender"])

    # back notes (handwritten) — numbered after the front notes
    k = note_start
    for note in [n for n in content.notes if n.side == "back"]:
        for _ in range(30):
            tile = note_tile(note, ppi, rng)
            x = rng.uniform(W * 0.1, W * 0.9 - tile.width)
            y = rng.uniform(H * 0.55, H * 0.92 - tile.height)
            r = (int(x), int(y), int(x) + tile.width, int(y) + tile.height)
            if lay.free(r):
                key = f"note_{k}"
                out.boxes[key] = paste(img, tile, x, y)
                out.notes.append((note, key))
                lay.add(out.boxes[key])
                k += 1
                break

    # small printed text near the bottom
    if content.back_printed:
        st = print_style(rng, ppi, (0.06, 0.08), mono=False, color=INK_COLORS["gray"])
        tile = render_lines(content.back_printed, st, rng)
        x, y = (W - tile.width) / 2, H - ppi * 0.15 - tile.height
        out.boxes["back_text"] = paste(img, tile, x, y)

    # USPS-style fluorescent ID tag on the back
    if chance(rng, 0.3):
        bar_w, pitch, hgt = max(1, int(ppi * 0.015)), max(2, int(ppi * 0.035)), int(ppi * 0.12)
        n = 50
        tag = Image.new("RGBA", (n * pitch, hgt), (0, 0, 0, 0))
        dd = ImageDraw.Draw(tag)
        for i in range(n):
            top = 0 if rng.random() < 0.5 else hgt // 2
            dd.rectangle((i * pitch, top, i * pitch + bar_w, hgt), fill=(235, 120, 110, 200))
        x, y = W * rng.uniform(0.05, 0.4), H - ppi * rng.uniform(0.3, 0.45)
        r = (int(x), int(y), int(x) + tag.width, int(y) + tag.height)
        if lay.free(r, gap=2):
            out.boxes["id_tag"] = paste(img, tag, x, y)
    return out
