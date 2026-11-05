"""Rendering of text blocks (printed, typewriter, handwritten, rubber stamp) to RGBA tiles.

Each function returns a tightly-cropped RGBA PIL image. The caller pastes it on the
envelope and records the tile's rectangle as the element's bounding box, so boxes
always match the ink that was actually drawn.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fonts import get_font

INK_COLORS = {
    "black": (25, 25, 30),
    "blue": (25, 45, 140),
    "darkblue": (20, 30, 90),
    "pencil": (85, 85, 90),
    "red": (180, 30, 35),
    "purple": (95, 35, 120),
    "gray": (70, 70, 75),
}


@dataclass
class TextStyle:
    font: str
    size: int
    color: tuple = INK_COLORS["black"]
    handwritten: bool = False
    jitter: float = 1.0          # handwriting messiness multiplier (0 = none, 1 normal, 3 messy)
    line_spacing: float = 1.18
    align: str = "left"          # left | center
    slant_deg: float = 0.0       # whole-block rotation (handwriting drift), degrees CCW
    alpha: float = 1.0           # ink opacity (pencil / faded ink)
    bold: int = 0                # stroke width in px
    char_level: bool = False     # per-character jitter (messy handwriting / typewriter)
    squeeze: float = 1.0         # character advance multiplier (<1 = letters crowd / overlap)


def _crop_alpha(img: Image.Image, pad: int = 2) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        return img.crop((0, 0, 1, 1))
    x0, y0, x1, y1 = bbox
    return img.crop((max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad)))


def _word_tile(word: str, font, color, stroke: int) -> Image.Image:
    l, t, r, b = font.getbbox(word, anchor="ls", stroke_width=stroke)
    w, h = r - l + 4, b - t + 4
    tile = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((-l + 2, -t + 2), word, font=font, fill=color + (255,), anchor="ls",
                              stroke_width=stroke, stroke_fill=color + (255,))
    # tile carries the baseline offset so callers can align baselines
    tile.info["baseline"] = -t + 2
    return tile


def render_lines(lines: list[str], style: TextStyle, rng: np.random.Generator) -> Image.Image:
    font = get_font(style.font, style.size)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * style.line_spacing)
    widths = [font.getlength(ln) for ln in lines] or [1]
    W = int(max(widths) * (1.6 if style.handwritten else 1.1)) + style.size * 2
    H = int(line_h * (len(lines) + 1.5)) + style.size
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    j = style.jitter if style.handwritten else 0.0

    y = style.size + ascent
    indent_drift = 0.0
    for ln, lw in zip(lines, widths):
        x = style.size + (max(widths) - lw) / 2 if style.align == "center" else style.size
        if style.handwritten:
            indent_drift += rng.normal(0, 0.15 * style.size * j)
            x += indent_drift
        line_slope = rng.normal(0, 0.012 * j)
        start_x = x
        words = ln.split(" ")
        for wi, word in enumerate(words):
            if not word:
                x += font.getlength(" ")
                continue
            size = style.size
            if style.handwritten:
                size = max(8, int(style.size * (1 + rng.normal(0, 0.05 * j))))
            f = get_font(style.font, size)
            units = list(word) if (style.char_level and len(word) > 0) else [word]
            for unit in units:
                tile = _word_tile(unit, f, style.color, style.bold)
                base = tile.info["baseline"]
                if style.handwritten:
                    ang = rng.normal(0, 2.0 * j)
                    tile = tile.rotate(ang, resample=Image.BICUBIC, expand=True)
                dy = (x - start_x) * line_slope
                if style.handwritten:
                    dy += rng.normal(0, 0.05 * style.size * j)
                elif style.char_level:  # typewriter: slight per-character misalignment
                    dy += rng.normal(0, 0.03 * style.size)
                px, py = int(round(x)), int(round(y - base + dy))
                canvas.alpha_composite(tile, (max(0, px), max(0, py)))
                adv = f.getlength(unit) * (style.squeeze if style.char_level else 1.0)
                if style.handwritten and style.char_level:
                    adv *= 1 + rng.normal(0, 0.08 * j)
                x += adv
            if wi < len(words) - 1:
                sp = f.getlength(" ")
                x += sp * (rng.uniform(0.85, 1.5) if style.handwritten else 1.0)
        y += line_h * (1 + (rng.normal(0, 0.06 * j) if style.handwritten else 0))

    if style.alpha < 1.0 or style.color == INK_COLORS["pencil"]:
        a = np.asarray(canvas.getchannel("A"), dtype=np.float32)
        tex = 1.0 if style.color != INK_COLORS["pencil"] else rng.uniform(0.55, 1.0, a.shape)
        canvas.putalpha(Image.fromarray(np.clip(a * style.alpha * tex, 0, 255).astype(np.uint8)))
    if style.slant_deg:
        canvas = canvas.rotate(style.slant_deg, resample=Image.BICUBIC, expand=True)
    return _crop_alpha(canvas)


def render_rubber_stamp(text: str, font_path: str, size: int, color, rng: np.random.Generator) -> Image.Image:
    font = get_font(font_path, size)
    l, t, r, b = font.getbbox(text)
    padx, pady = int(size * 0.45), int(size * 0.35)
    bw = max(2, size // 9)
    w, h = (r - l) + 2 * padx, (b - t) + 2 * pady
    tile = Image.new("RGBA", (w + 4 * bw, h + 4 * bw), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rectangle((bw, bw, w + 3 * bw, h + 3 * bw), outline=color + (255,), width=bw)
    d.text((2 * bw + padx - l, 2 * bw + pady - t), text, font=font, fill=color + (255,))
    # Uneven ink: knock out speckles, fade one side.
    a = np.asarray(tile.getchannel("A"), dtype=np.float32) / 255.0
    noise = rng.random(a.shape).astype(np.float32)
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)),
                       dtype=np.float32) / 255.0
    grad = np.linspace(rng.uniform(0.55, 0.85), 1.0, a.shape[1], dtype=np.float32)[None, :]
    if rng.random() < 0.5:
        grad = grad[:, ::-1]
    a = a * (noise > rng.uniform(0.3, 0.42)) * grad * rng.uniform(0.75, 0.95)
    tile.putalpha(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)))
    tile = tile.rotate(rng.uniform(-14, 14), resample=Image.BICUBIC, expand=True)
    return _crop_alpha(tile)
