"""Procedural backgrounds the envelope is photographed on (desk, table, fabric, clutter)."""
from __future__ import annotations

import cv2
import numpy as np


def _lowfreq(rng, H, W, cells, sigma=0.0):
    small = rng.normal(0, 1, (max(2, H // cells), max(2, W // cells))).astype(np.float32)
    if sigma:  # smooth at low resolution (equivalent to blurring the upscaled field, far cheaper)
        small = cv2.GaussianBlur(small, (0, 0), max(0.3, sigma / cells))
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)


def solid(rng, H, W):
    palette = [(0.18, 0.18, 0.2), (0.32, 0.3, 0.28), (0.55, 0.55, 0.57), (0.12, 0.2, 0.3), (0.62, 0.6, 0.55),
               (0.2, 0.28, 0.22), (0.45, 0.32, 0.25), (0.82, 0.8, 0.76)]
    c = np.array(palette[int(rng.integers(len(palette)))], np.float32) * rng.uniform(0.85, 1.15)
    img = np.empty((H, W, 3), np.float32)
    img[:] = c
    img *= (1 + 0.04 * _lowfreq(rng, H, W, 100, 8))[..., None]
    return img


def wood(rng, H, W):
    tones = [((0.55, 0.36, 0.2), (0.42, 0.26, 0.14)), ((0.72, 0.55, 0.36), (0.6, 0.43, 0.27)),
             ((0.35, 0.22, 0.13), (0.25, 0.15, 0.09)), ((0.8, 0.68, 0.5), (0.68, 0.55, 0.38))]
    a, b = (np.array(t, np.float32) for t in tones[int(rng.integers(len(tones)))])
    D = int(np.hypot(H, W)) + 4
    # warp field stretched along the grain (x) so rings become long, gently wavy lines
    small = rng.normal(0, 1, (max(2, D // 25), max(2, D // 160))).astype(np.float32)
    warp = cv2.resize(cv2.GaussianBlur(small, (0, 0), 0.8), (D, D), interpolation=cv2.INTER_CUBIC)
    yy = np.arange(D, dtype=np.float32)[:, None]
    freq = rng.uniform(0.12, 0.3)
    phase = yy * freq + warp * rng.uniform(1.5, 3.0)
    grain = 0.5 + 0.5 * np.sin(phase)
    fine = 0.5 + 0.5 * np.sin(phase * 5.3 + 1.7)
    streak = cv2.resize(rng.random((D, max(2, D // 40))).astype(np.float32), (D, D), interpolation=cv2.INTER_LINEAR)
    t = np.clip(0.6 * grain ** 3 + 0.2 * fine + 0.2 * streak, 0, 1)[..., None]
    img = a * (1 - t) + b * t
    M = cv2.getRotationMatrix2D((D / 2, D / 2), rng.choice([0.0, 90.0]) + rng.normal(0, 4), 1.0)
    img = cv2.warpAffine(img, M, (D, D), borderMode=cv2.BORDER_REFLECT)
    y0, x0 = (D - H) // 2, (D - W) // 2
    img = img[y0:y0 + H, x0:x0 + W]
    if rng.random() < 0.6:   # plank seams
        horiz = abs(M[0, 1]) < 0.5
        for _ in range(int(rng.integers(1, 3))):
            if horiz:
                y = int(rng.integers(0, H))
                img[max(0, y - 1):y + 1, :] *= 0.55
            else:
                x = int(rng.integers(0, W))
                img[:, max(0, x - 1):x + 1] *= 0.55
    return img


def laminate(rng, H, W):
    base = np.array([(0.85, 0.85, 0.83), (0.78, 0.76, 0.72), (0.6, 0.6, 0.62), (0.92, 0.9, 0.86),
                     (0.4, 0.42, 0.45)][int(rng.integers(5))], np.float32)
    img = np.empty((H, W, 3), np.float32)
    img[:] = base
    speck = rng.standard_normal((H, W), dtype=np.float32) * 0.03
    img += cv2.GaussianBlur(speck, (0, 0), 0.8)[..., None]
    img *= (1 + 0.03 * _lowfreq(rng, H, W, 80, 10))[..., None]
    return img


def fabric(rng, H, W):
    c1 = rng.uniform(0.2, 0.8, 3).astype(np.float32)
    c2 = np.clip(c1 * rng.uniform(0.6, 0.9), 0, 1)
    yy = np.arange(H, dtype=np.float32)[:, None]
    xx = np.arange(W, dtype=np.float32)[None, :]
    weave = 0.5 + 0.25 * np.sin(xx * 2.6) + 0.25 * np.sin(yy * 2.6)
    img = c1 * (1 - 0.15 * weave[..., None])
    if rng.random() < 0.5:  # plaid / gingham
        p = rng.uniform(20, 45)
        band = (((xx // p) % 2 + (yy // p) % 2) / 2)[..., None]
        img = img * (1 - band) + c2 * band
    return img


def clutter(rng, H, W):
    img = (wood if rng.random() < 0.5 else laminate)(rng, H, W).copy()
    n = int(rng.integers(3, 8))
    for _ in range(n):
        kind = rng.choice(["paper", "sticky", "pen", "ring", "card"])
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        ang = rng.uniform(0, 180)
        if kind in ("paper", "card", "sticky"):
            if kind == "paper":
                w, h, col = rng.uniform(150, 350), rng.uniform(190, 450), (0.93, 0.93, 0.9)
            elif kind == "card":
                w, h, col = rng.uniform(100, 170), rng.uniform(60, 105), tuple(rng.uniform(0.3, 0.9, 3))
            else:
                w, h, col = rng.uniform(55, 85), rng.uniform(55, 85), (0.98, 0.9, 0.45)
            box = cv2.boxPoints(((cx, cy), (w, h), ang)).astype(np.int32)
            shadow = np.zeros((H, W), np.float32)
            cv2.fillPoly(shadow, [box + np.array([3, 4], dtype=np.int32)], 1.0)
            img *= (1 - 0.25 * cv2.GaussianBlur(shadow, (0, 0), 3))[..., None]
            cv2.fillPoly(img, [box], tuple(float(c) for c in col))
            if kind == "paper":  # faint text lines
                for k in range(int(rng.integers(5, 15))):
                    t = (k + 1) / 16
                    p0 = box[0] + (box[3] - box[0]) * t + (box[1] - box[0]) * 0.1
                    p1 = box[0] + (box[3] - box[0]) * t + (box[1] - box[0]) * rng.uniform(0.4, 0.9)
                    cv2.line(img, tuple(int(v) for v in p0), tuple(int(v) for v in p1), (0.55, 0.55, 0.6), 2)
        elif kind == "pen":
            length = rng.uniform(125, 225)
            box = cv2.boxPoints(((cx, cy), (length, rng.uniform(7, 11)), ang)).astype(np.int32)
            col = tuple(float(c) for c in rng.choice([[0.1, 0.1, 0.12], [0.1, 0.2, 0.6], [0.7, 0.1, 0.1]]))
            cv2.fillPoly(img, [box], col)
        else:  # coffee ring
            r = int(rng.uniform(25, 45))
            ring = np.zeros((H, W), np.float32)
            cv2.circle(ring, (int(cx), int(cy)), r, 1.0, int(rng.integers(2, 4)))
            ring = cv2.GaussianBlur(ring, (0, 0), 2)
            img = img * (1 - 0.35 * ring[..., None]) + np.array([0.35, 0.22, 0.1], np.float32) * 0.35 * ring[..., None]
    return img


KINDS = {"solid": solid, "wood": wood, "laminate": laminate, "fabric": fabric, "clutter": clutter}


def make_background(kind: str, rng, H: int, W: int) -> np.ndarray:
    """Return uint8 HxWx3 RGB.

    Built at half resolution and upscaled: the background is soft, out of the focal
    plane and mostly hidden, so the detail loss is invisible and it is ~4x faster.
    """
    h, w = max(2, H // 2), max(2, W // 2)
    small = KINDS[kind](rng, h, w)
    small = (np.clip(small, 0, 1) * 255 + 0.5).astype(np.uint8)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
