"""Fast deterministic noise: one fixed Gaussian tile per process, sampled at a random offset.

Generating fresh full-resolution Gaussian noise for every image is one of the most
expensive steps; cropping a pre-generated tile (fixed seed) at an rng-chosen offset and
orientation is ~50x faster and still fully deterministic.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

TILE = 2048


@lru_cache(maxsize=2)
def _tile(channels: int) -> np.ndarray:
    rng = np.random.default_rng(20260101 + channels)
    return rng.standard_normal((TILE, TILE, channels), dtype=np.float32)


def gaussian(rng: np.random.Generator, H: int, W: int, channels: int = 1) -> np.ndarray:
    """Standard-normal noise of shape (H, W, channels)."""
    if H > TILE or W > TILE:
        return rng.standard_normal((H, W, channels), dtype=np.float32)
    t = _tile(channels)
    k = int(rng.integers(4))
    if k & 1:
        t = t[::-1]
    if k & 2:
        t = t[:, ::-1]
    y, x = int(rng.integers(0, TILE - H + 1)), int(rng.integers(0, TILE - W + 1))
    return t[y:y + H, x:x + W]


SCALE = 64.0  # int16 noise tile has standard deviation SCALE


@lru_cache(maxsize=1)
def _sensor_tile() -> np.ndarray:
    rng = np.random.default_rng(20260202)
    lum = rng.standard_normal((TILE, TILE, 1), dtype=np.float32)
    chroma = rng.standard_normal((TILE, TILE, 3), dtype=np.float32) * 0.35
    n = (lum + chroma) / np.sqrt(1 + 0.35 ** 2)
    return np.clip(n * SCALE, -32000, 32000).astype(np.int16)


def sensor_noise(rng: np.random.Generator, H: int, W: int) -> np.ndarray:
    """int16 (H, W, 3) correlated luma+chroma noise with std SCALE."""
    t = _sensor_tile()
    if H > TILE or W > TILE:
        t = np.tile(t, (H // TILE + 1, W // TILE + 1, 1))
    k = int(rng.integers(4))
    if k & 1:
        t = t[::-1]
    if k & 2:
        t = t[:, ::-1]
    y, x = int(rng.integers(0, t.shape[0] - H + 1)), int(rng.integers(0, t.shape[1] - W + 1))
    return np.ascontiguousarray(t[y:y + H, x:x + W])
