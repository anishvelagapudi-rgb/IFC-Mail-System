"""Config loading: YAML file + CLI overrides."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    with open(path or DEFAULT_CONFIG) as f:
        cfg = yaml.safe_load(f)
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        node = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return cfg


def augment_preset(cfg: dict, strength: str) -> dict:
    presets = cfg["augment"]
    if strength not in presets:
        raise ValueError(f"unknown augment strength {strength!r}; choose from {list(presets)}")
    return copy.deepcopy(presets[strength])
