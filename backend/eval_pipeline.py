"""Run the image pipeline over a sample of the synthetic dataset and score it with the existing
evaluator (dataset-generator/evaluate.py).

    python -m backend.eval_pipeline --data dataset-generator/dataset --sample 50 --seed 1

Writes one {id}.json prediction per sample to --out (default: predictions/pipeline/), then
prints the evaluator's report. Each sample is one API call with two images, so this costs
money: --sample 50 on claude-haiku-5-5 is a few cents. Synthetic data only.
"""
import argparse
import json
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config, pipeline

ROOT = Path(__file__).resolve().parent.parent


def predict(label_path: Path, data_dir: Path, out_dir: Path, min_conf: float) -> dict:
    label = json.loads(label_path.read_text())
    front = (data_dir / label["images"]["front"]["file"]).read_bytes()
    back = (data_dir / label["images"]["back"]["file"]).read_bytes()
    t = time.time()
    result = pipeline.extract(front, back, min_conf)
    pred = pipeline.for_client(result)
    pred["id"] = label["id"]
    pred["seconds"] = round(time.time() - t, 2)
    pred["usage"] = result.get("usage")
    (out_dir / f"{label['id']}.json").write_text(json.dumps(pred, indent=2))
    return pred


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "dataset-generator" / "dataset"))
    ap.add_argument("--out", default=str(ROOT / "predictions" / "pipeline"))
    ap.add_argument("--sample", type=int, default=50, help="how many samples (0 = all)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--min-confidence", type=float, default=0.7)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", help="also write the evaluator report to this file")
    args = ap.parse_args()

    if not config.ANTHROPIC_API_KEY:
        sys.exit("Set ANTHROPIC_API_KEY first.")
    data = Path(args.data)
    labels = sorted((data / "labels").glob("*.json"))
    if not labels:
        sys.exit(f"No labels in {data}/labels. Generate a dataset first (see dataset-generator/README.md).")
    if args.sample and args.sample < len(labels):
        labels = random.Random(args.seed).sample(labels, args.sample)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()  # the evaluator scores every label, so keep only this run's predictions...

    print(f"Running {config.PIPELINE_MODEL} on {len(labels)} samples...")
    with ThreadPoolExecutor(args.workers) as pool:
        preds = list(pool.map(lambda p: predict(p, data, out, args.min_confidence), labels))

    errors = [p for p in preds if p["processing"].get("error")]
    tokens_in = sum((p.get("usage") or {}).get("input_tokens", 0) for p in preds)
    tokens_out = sum((p.get("usage") or {}).get("output_tokens", 0) for p in preds)
    print(f"Done. {len(errors)} fell back to manual. Tokens: {tokens_in} in / {tokens_out} out. "
          f"Mean {sum(p['seconds'] for p in preds) / len(preds):.1f}s per item.")
    if errors:
        print("  e.g.", errors[0]["processing"]["error"])

    # ...and score only the sampled ids, by pointing the evaluator at a labels folder of just those.
    sub = out.parent / f"{out.name}_labels"
    (sub / "labels").mkdir(parents=True, exist_ok=True)
    for old in (sub / "labels").glob("*.json"):
        old.unlink()
    for p in labels:
        (sub / "labels" / p.name).write_text(p.read_text())
    cmd = [sys.executable, str(ROOT / "dataset-generator" / "evaluate.py"), "--data", str(sub), "--predictions", str(out)]
    if args.json:
        cmd += ["--json", args.json]
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
