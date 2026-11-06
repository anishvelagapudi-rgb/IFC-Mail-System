"""Score the Claude envelope reader on the synthetic dataset, using dataset-generator/evaluate.py.

    python server/eval_pipeline.py --sample 20

Each sample is one Claude call with two photos, so this costs a little money
(20 samples on claude-haiku-5-5 is around a cent). Synthetic data only.
"""
import argparse
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "dataset-generator" / "dataset"))
    ap.add_argument("--sample", type=int, default=20, help="how many envelopes (0 = all)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "predictions" / "claude"))
    args = ap.parse_args()

    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Put your ANTHROPIC_API_KEY in .env first (see README).")
    data = Path(args.data)
    labels = sorted((data / "labels").glob("*.json"))
    if not labels:
        sys.exit(f"No labels in {data}/labels. Generate a dataset first (see dataset-generator/README.md).")
    if args.sample and args.sample < len(labels):
        labels = random.Random(args.seed).sample(labels, args.sample)

    out = Path(args.out)
    (out / "pred").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    for old in [*(out / "pred").glob("*.json"), *(out / "labels").glob("*.json")]:
        old.unlink()

    def run(label_path: Path):
        label = json.loads(label_path.read_text())
        front = (data / label["images"]["front"]["file"]).read_bytes()
        back = (data / label["images"]["back"]["file"]).read_bytes()
        pred = pipeline.read_envelope(front, back)
        (out / "pred" / f"{label['id']}.json").write_text(json.dumps(pred, indent=2))
        (out / "labels" / label_path.name).write_text(label_path.read_text())  # score only the sampled ids
        return pred

    print(f"Reading {len(labels)} envelopes with {pipeline.MODEL}...")
    with ThreadPoolExecutor(4) as pool:
        preds = list(pool.map(run, labels))
    failed = [p for p in preds if p["source"] == "manual"]
    print(f"{len(failed)} fell back to manual." + (f" e.g. {failed[0].get('error')}" if failed else ""))

    sys.exit(subprocess.call([sys.executable, str(ROOT / "dataset-generator" / "evaluate.py"),
                              "--data", str(out), "--predictions", str(out / "pred")]))


if __name__ == "__main__":
    main()
