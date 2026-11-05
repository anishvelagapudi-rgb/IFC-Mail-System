"""Deliberate damage for illegible samples, applied in flat-envelope / sheet coordinates.

(heavy_blur and extreme_low_light are photographic and handled by augment.py;
messy_handwriting is handled at render time.)
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw

Rect = tuple[int, int, int, int]


def _blob_mask(rng, H, W, box: Rect, cover: float) -> np.ndarray:
    """Irregular blob centred on box, roughly `cover` x the box size."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2 + rng.normal(0, (x1 - x0) * 0.08), (y0 + y1) / 2 + rng.normal(0, (y1 - y0) * 0.08)
    rx, ry = (x1 - x0) / 2 * cover, (y1 - y0) / 2 * cover * 1.25
    yy = np.arange(H, dtype=np.float32)[:, None]
    xx = np.arange(W, dtype=np.float32)[None, :]
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    small = rng.normal(0, 1, (max(2, H // 50), max(2, W // 50))).astype(np.float32)
    n = cv2.GaussianBlur(cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC), (0, 0), 10)
    m = (d + 0.35 * n < 1.0).astype(np.float32)
    return cv2.GaussianBlur(m, (0, 0), 3)


def water_damage(img: Image.Image, box: Rect, rng, text_px: int) -> dict:
    a = np.asarray(img, dtype=np.float32)
    H, W = a.shape[:2]
    mask = _blob_mask(rng, H, W, box, rng.uniform(1.05, 1.35))[..., None]
    # ink bleed: spread dark ink, then blur
    k = max(3, int(text_px * 0.25) | 1)
    bled = cv2.erode(a, np.ones((k, k), np.uint8))
    sigma = text_px * rng.uniform(0.28, 0.45)
    bled = cv2.GaussianBlur(0.5 * bled + 0.5 * a, (0, 0), sigma)
    paper = np.median(a.reshape(-1, 3), axis=0)
    bled = 0.55 * bled + 0.45 * paper              # washed out
    tint = np.array([0.93, 0.86, 0.72], np.float32) * rng.uniform(0.92, 1.0)
    out = a * (1 - mask) + bled * tint * mask
    # tide-line at the stain edge
    edge = cv2.GaussianBlur(np.abs(cv2.Laplacian(mask[..., 0], cv2.CV_32F, ksize=5)), (0, 0), 2)
    edge = edge / (edge.max() + 1e-6)
    out *= (1 - 0.3 * edge)[..., None]
    img.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)))
    ys, xs = np.nonzero(mask[..., 0] > 0.2)
    return {"stain_box": (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), "blur_sigma": float(sigma)}


def smudge(img: Image.Image, box: Rect, rng, text_px: int) -> dict:
    a = np.asarray(img, dtype=np.float32)
    H, W = a.shape[:2]
    mask = _blob_mask(rng, H, W, box, rng.uniform(1.0, 1.25))[..., None]
    L = max(9, int(text_px * rng.uniform(2.2, 3.5)))
    ang = rng.uniform(-30, 30)
    kern = np.zeros((L, L), np.float32)
    kern[L // 2, :] = 1
    kern = cv2.warpAffine(kern, cv2.getRotationMatrix2D((L / 2, L / 2), ang, 1), (L, L))
    kern /= kern.sum()
    smeared = cv2.filter2D(a, -1, kern)
    smeared = cv2.GaussianBlur(smeared, (0, 0), text_px * 0.12)
    graphite = np.array([110, 108, 112], np.float32)
    g = rng.uniform(0.15, 0.3)
    out = a * (1 - mask) + (smeared * (1 - g) + graphite * g) * mask
    img.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)))
    return {"smear_length_px": L, "smear_angle_deg": float(ang)}


def sticker_cover(img: Image.Image, box: Rect, rng, ppi: float) -> dict:
    """Opaque label stuck over most of the recipient block. Returns the sticker rect."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cover_w = rng.uniform(0.85, 1.05)
    cover_h = rng.uniform(0.6, 0.95)
    sw, sh = int(bw * cover_w + ppi * 0.1), int(bh * cover_h + ppi * 0.08)
    sx = x0 - ppi * rng.uniform(0.03, 0.1)              # starts left of the text
    sy = y0 - ppi * rng.uniform(0.03, 0.08)             # always hides the first (name) line
    col = [(250, 250, 248), (250, 222, 80), (255, 170, 60), (240, 240, 232), (200, 230, 250)][int(rng.integers(5))]
    st = Image.new("RGBA", (sw, sh), col + (255,))
    d = ImageDraw.Draw(st)
    d.rectangle((0, 0, sw - 1, sh - 1), outline=tuple(int(c * 0.8) for c in col) + (255,), width=2)
    if rng.random() < 0.5:  # barcode-ish print on the sticker
        x = int(sw * 0.1)
        while x < sw * 0.9:
            w = int(rng.integers(1, 5))
            d.rectangle((x, sh * 0.3, x + w, sh * 0.7), fill=(30, 30, 30, 255))
            x += w + int(rng.integers(1, 5))
    ang = rng.uniform(-3, 3)
    st = st.rotate(ang, resample=Image.BICUBIC, expand=True)
    # shadow
    sh_img = Image.new("RGBA", st.size, (0, 0, 0, 50))
    sh_img.putalpha(st.getchannel("A").point(lambda v: v // 5))
    img.paste(sh_img, (int(sx) + 3, int(sy) + 3), sh_img)
    img.paste(st, (int(sx), int(sy)), st)
    return {"occluder_box": (int(sx), int(sy), int(sx) + st.width, int(sy) + st.height)}


def overlapping_envelope(sheet: np.ndarray, box: Rect, env_rect: Rect, rng, font_path: str) -> dict:
    """Draw another envelope lying on top of this one, covering most of `box`.

    sheet is HxWx4 uint8 in sheet coordinates (the padded canvas); modified in place.
    Returns the occluder polygon (4 corners) in sheet coordinates.
    """
    from .fonts import get_font  # local import to avoid cycles

    x0, y0, x1, y1 = box
    ex0, ey0, ex1, ey1 = env_rect
    bh = y1 - y0
    name_strip = (x0, y0, x1, y0 + max(4, int(bh * 0.3)))   # first line(s): the recipient name
    best = None
    for _ in range(60):
        ow, oh = (ex1 - ex0) * rng.uniform(0.7, 1.0), (ey1 - ey0) * rng.uniform(0.75, 1.1)
        ang = rng.uniform(-25, 25)
        side = rng.choice([-1, 1])
        cover = rng.uniform(0.6, 0.95)
        corner_x = x0 + (x1 - x0) * (1 - cover) if side > 0 else x1 - (x1 - x0) * (1 - cover)
        corner_y = y0 - bh * rng.uniform(0.05, 0.35)
        cx = corner_x + side * ow / 2
        cy = corner_y + oh / 2
        poly = cv2.boxPoints(((cx, cy), (ow, oh), ang)).astype(np.float32)
        score = (covered_fraction(name_strip, poly), covered_fraction(box, poly))
        if best is None or score > best[0]:
            best = (score, poly, cx, cy, ow, oh, ang)
        if score[0] >= 0.9 and score[1] >= 0.6:
            break
    _, poly, cx, cy, ow, oh, ang = best
    # make sure the occluder's near edge actually crosses the block
    H, W = sheet.shape[:2]
    col = [(238, 236, 228), (215, 185, 135), (225, 232, 240), (250, 250, 248)][int(rng.integers(4))]
    shadow = np.zeros((H, W), np.float32)
    cv2.fillPoly(shadow, [(poly + [8, 10]).astype(np.int32)], 1.0)
    shadow = cv2.GaussianBlur(shadow, (0, 0), 9)
    rgb = sheet[..., :3].astype(np.float32) * (1 - 0.35 * shadow[..., None])
    alpha = np.maximum(sheet[..., 3].astype(np.float32), shadow * 140)
    layer = np.zeros((H, W), np.uint8)
    cv2.fillPoly(layer, [poly.astype(np.int32)], 255)
    m = layer[..., None] > 0
    rgb = np.where(m, np.array(col, np.float32) + rng.normal(0, 2, (H, W, 1)).astype(np.float32), rgb)
    sheet[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    sheet[..., 3] = np.where(layer > 0, 255, np.clip(alpha, 0, 255)).astype(np.uint8)
    # a few lines of unrelated text on the occluding envelope
    tile = Image.new("RGBA", (int(ow), int(oh)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    f = get_font(font_path, int(oh * 0.07))
    for k, line in enumerate(["OCCUPANT", "1600 W MAIN ST STE 4", "SPRINGVALE OH 44011"]):
        d.text((ow * 0.4, oh * 0.45 + k * oh * 0.09), line, font=f, fill=(30, 30, 35, 255))
    tile = tile.rotate(-ang, resample=Image.BICUBIC, expand=True)
    tx, ty = int(cx - tile.width / 2), int(cy - tile.height / 2)
    sx0, sy0 = max(0, tx), max(0, ty)
    sx1, sy1 = min(W, tx + tile.width), min(H, ty + tile.height)
    if sx1 > sx0 and sy1 > sy0:
        t = np.asarray(tile, dtype=np.float32)[sy0 - ty:sy1 - ty, sx0 - tx:sx1 - tx]
        ta = (t[..., 3:] / 255.0) * (layer[sy0:sy1, sx0:sx1, None] > 0)
        region = sheet[sy0:sy1, sx0:sx1, :3].astype(np.float32)
        sheet[sy0:sy1, sx0:sx1, :3] = np.clip(region * (1 - ta) + t[..., :3] * ta, 0, 255).astype(np.uint8)
    return {"occluder_polygon": poly.tolist()}


def covered_fraction(box: Rect, occluder_poly: np.ndarray) -> float:
    x0, y0, x1, y1 = box
    rect = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float32)
    area, _ = cv2.intersectConvexConvex(rect, np.asarray(occluder_poly, np.float32))
    return float(area / max(1.0, (x1 - x0) * (y1 - y0)))
