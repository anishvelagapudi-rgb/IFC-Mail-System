#!/usr/bin/env python3
"""Generate a synthetic dataset of photographed mail envelopes with ground-truth labels.

Example:
    python generate.py --count 5000 --seed 42 --out dataset/ --illegible-rate 0.1 --augment-strength medium

Output is deterministic for a given (seed, config): sample i depends only on the seed and
its index, so results are identical regardless of --workers or --count.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import yaml

from mailgen import __version__
from mailgen.config import load_config
from mailgen.fonts import font_catalog
from mailgen.sample import MANIFEST_FIELDS, generate_sample

HERE = Path(__file__).resolve().parent
_CTX: dict = {}


def _init_worker(cfg, seed, strength, out_dir):
    import cv2
    cv2.setNumThreads(1)
    _CTX.update(cfg=cfg, seed=seed, strength=strength, out_dir=Path(out_dir))


def _work(index: int) -> dict:
    return generate_sample(index, _CTX["cfg"], _CTX["seed"], _CTX["strength"], _CTX["out_dir"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=100, help="number of mail items to generate")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(HERE / "dataset"), help="output folder (default: dataset-generator/dataset)")
    ap.add_argument("--config", default=None, help="config YAML (default: ./config.yaml)")
    ap.add_argument("--illegible-rate", type=float, default=None, help="override config illegible_rate")
    ap.add_argument("--augment-strength", default="medium", choices=["none", "light", "medium", "heavy"])
    ap.add_argument("--start-index", type=int, default=0, help="first sample index (for sharded generation)")
    ap.add_argument("--workers", type=int, default=0, help="processes (default: CPU count)")
    ap.add_argument("--overwrite", action="store_true", help="delete an existing output folder first")
    args = ap.parse_args(argv)

    cfg = load_config(args.config, {"illegible_rate": args.illegible_rate})
    font_catalog()  # fail early if fonts are missing
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        if not args.overwrite:
            print(f"{out}/ is not empty; pass --overwrite to replace it", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)

    indices = list(range(args.start_index, args.start_index + args.count))
    workers = args.workers or os.cpu_count() or 1
    t0 = time.time()
    rows = []
    initargs = (cfg, args.seed, args.augment_strength, str(out))
    if workers == 1:
        _init_worker(*initargs)
        for k, i in enumerate(indices, 1):
            rows.append(_work(i))
            _progress(k, len(indices), t0)
    else:
        with Pool(workers, initializer=_init_worker, initargs=initargs) as pool:
            for k, row in enumerate(pool.imap_unordered(_work, indices, chunksize=4), 1):
                rows.append(row)
                _progress(k, len(indices), t0)
    print()
    rows.sort(key=lambda r: r["id"])
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[r["legibility"]] = counts.get(r["legibility"], 0) + 1
    info = {"generator_version": __version__, "count": len(rows), "seed": args.seed,
            "start_index": args.start_index, "augment_strength": args.augment_strength,
            "legibility_counts": counts, "seconds": round(time.time() - t0, 1)}
    (out / "dataset_info.json").write_text(json.dumps(info, indent=2))
    (out / "config_used.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    dt = time.time() - t0
    print(f"wrote {len(rows)} samples to {out}/ in {dt:.1f}s ({len(rows) / max(dt, 1e-6):.1f}/s) "
          f"legibility={counts}")
    return 0


def _progress(k, n, t0):
    if k == n or k % 25 == 0:
        rate = k / max(time.time() - t0, 1e-6)
        print(f"\r{k}/{n}  {rate:.1f} samples/s", end="", flush=True)


if __name__ == "__main__":
    sys.exit(main())
