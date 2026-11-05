"""Font lookup and caching (fonts are downloaded by setup_fonts.py)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import ImageFont

from .config import ROOT

FONT_DIR = ROOT / "fonts"


@lru_cache(maxsize=1)
def font_catalog() -> dict[str, list[str]]:
    manifest = FONT_DIR / "fonts.json"
    if not manifest.exists():
        raise SystemExit("fonts/ is missing. Run:  python dataset-generator/setup_fonts.py")
    cats: dict[str, list[str]] = {}
    for entry in json.loads(manifest.read_text())["fonts"]:
        cats.setdefault(entry["category"], []).append(str(FONT_DIR / entry["file"]))
    return cats


def pick_font(rng: np.random.Generator, category: str) -> str:
    choices = font_catalog()[category]
    return choices[int(rng.integers(len(choices)))]


@lru_cache(maxsize=512)
def get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(6, int(size)))


@lru_cache(maxsize=4096)
def has_glyph(path: str, ch: str) -> bool:
    """True if the font has a real glyph for ch (not the .notdef box)."""
    if ch.isspace():
        return True
    font = get_font(path, 40)
    probe = bytes(font.getmask(ch))
    notdef = bytes(font.getmask("￿"))
    return probe != notdef and len(probe) > 0
