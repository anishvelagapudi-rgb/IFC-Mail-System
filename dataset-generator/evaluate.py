#!/usr/bin/env python3
"""Score a mail-pipeline's predictions against the synthetic dataset labels.

    python evaluate.py --data dataset/ --predictions preds/ [--json report.json]

Predictions folder: one {id}.json per sample, same shape as the labels, with any subset
of fields. Recognised fields:
    recipient.name, sender.name, sender.organization, notes (list of strings)
    illegible flag: "legibility": "illegible"  or  "illegible": true  (either works)

Scoring rules
  * Field accuracy (exact match + character error rate) is computed ONLY on samples whose
    true legibility is "clear" or "degraded".
  * Samples whose true legibility is "illegible" are scored ONLY through the illegible
    flag (precision / recall), and we report how many of them the pipeline tried to read
    instead of flagging.
  * A sample with no prediction file counts as "not flagged" with empty fields.
  * A field that is absent from EVERY prediction file is reported as "not predicted" and
    skipped; if it is present in some files, absence elsewhere counts as an empty answer.
  * A ground-truth null (e.g. sender.name for an organization with no person printed) is
    the empty string: predicting nothing is correct, predicting text is an insertion error.

Exact match is reported two ways: "em" (case-insensitive, whitespace-collapsed, Unicode
NFKC) and "em_strict" (raw string equality). CER uses the normalized strings and is
micro-averaged: total edit distance / total reference characters.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

FIELDS = {
    "recipient.name": ("recipient", "name"),
    "sender.name": ("sender", "name"),
    "sender.organization": ("sender", "organization"),
}
MISSING = object()


# --------------------------------------------------------------------------- text utils


def norm(s) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return " ".join(s.split())


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def get_path(d: dict, path: tuple):
    node = d
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return MISSING
        node = node[k]
    return node


def is_flagged(pred: dict | None) -> bool:
    if not pred:
        return False
    if pred.get("illegible") is True or pred.get("flag_illegible") is True:
        return True
    return str(pred.get("legibility", "")).lower() == "illegible"


# --------------------------------------------------------------------------- accumulators


class FieldStats:
    def __init__(self):
        self.n = self.em = self.em_strict = self.edits = self.ref_chars = 0

    def add(self, truth, pred):
        t, p = norm(truth), norm(pred)
        self.n += 1
        self.em += t == p
        self.em_strict += (truth or "") == (pred or "")
        self.edits += levenshtein(t, p)
        self.ref_chars += len(t)

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        return {"n": self.n, "em": self.em / self.n, "em_strict": self.em_strict / self.n,
                "cer": self.edits / max(1, self.ref_chars)}


class NoteStats:
    """Notes are an unordered list: pair predicted to true notes by smallest edit distance."""

    def __init__(self):
        self.n = self.em = self.tp = self.n_true = self.n_pred = self.edits = self.ref_chars = 0

    def add(self, truth: list, pred: list):
        t = [norm(x) for x in truth or []]
        p = [norm(x) for x in pred or []]
        self.n += 1
        self.n_true += len(t)
        self.n_pred += len(p)
        self.ref_chars += sum(len(x) for x in t)
        self.em += sorted(t) == sorted(p)
        pairs = sorted((levenshtein(a, b), i, j) for i, a in enumerate(t) for j, b in enumerate(p))
        used_t, used_p = set(), set()
        for d, i, j in pairs:
            if i in used_t or j in used_p:
                continue
            used_t.add(i)
            used_p.add(j)
            self.edits += d
            self.tp += d == 0
        self.edits += sum(len(t[i]) for i in range(len(t)) if i not in used_t)
        self.edits += sum(len(p[j]) for j in range(len(p)) if j not in used_p)

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        return {"n": self.n, "em": self.em / self.n, "cer": self.edits / max(1, self.ref_chars),
                "note_precision": self.tp / self.n_pred if self.n_pred else None,
                "note_recall": self.tp / self.n_true if self.n_true else None,
                "true_notes": self.n_true, "pred_notes": self.n_pred}


class FlagStats:
    def __init__(self):
        self.tp = self.fp = self.fn = self.tn = 0
        self.attempted_with_text = 0   # illegible, not flagged, AND a recipient name was guessed

    def add(self, truth_illegible: bool, flagged: bool, guessed_name: bool):
        if truth_illegible and flagged:
            self.tp += 1
        elif truth_illegible:
            self.fn += 1
            self.attempted_with_text += guessed_name
        elif flagged:
            self.fp += 1
        else:
            self.tn += 1

    def report(self) -> dict:
        p = self.tp / (self.tp + self.fp) if self.tp + self.fp else None
        r = self.tp / (self.tp + self.fn) if self.tp + self.fn else None
        f1 = 2 * p * r / (p + r) if p and r else None
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn, "precision": p, "recall": r, "f1": f1,
                "illegible_total": self.tp + self.fn,
                "illegible_attempted_not_flagged": self.fn,
                "illegible_attempted_with_recipient_guess": self.attempted_with_text,
                "flag_rate_on_readable": self.fp / (self.fp + self.tn) if self.fp + self.tn else None}


class Group:
    def __init__(self, fields):
        self.fields = {f: FieldStats() for f in fields}
        self.notes = NoteStats()
        self.flag = FlagStats()

    def report(self, with_notes: bool) -> dict:
        out = {f: s.report() for f, s in self.fields.items()}
        if with_notes:
            out["notes"] = self.notes.report()
        out["illegible_flag"] = self.flag.report()
        return out


# --------------------------------------------------------------------------- main


def evaluate(data: Path, pred_dir: Path) -> dict:
    label_dir = data / "labels" if (data / "labels").is_dir() else data
    labels = {p.stem: json.loads(p.read_text()) for p in sorted(label_dir.glob("*.json"))}
    if not labels:
        raise SystemExit(f"no label files in {label_dir}")
    preds = {}
    for p in sorted(pred_dir.glob("*.json")):
        try:
            preds[p.stem] = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            print(f"warning: could not parse {p}: {e}", file=sys.stderr)
    unknown = sorted(set(preds) - set(labels))

    # Which fields does the pipeline produce at all?
    present = {f for f, path in FIELDS.items() if any(get_path(pr, path) is not MISSING for pr in preds.values())}
    notes_present = any("notes" in pr for pr in preds.values())
    fields = [f for f in FIELDS if f in present]

    overall = Group(fields)
    groups: dict[str, dict[str, Group]] = defaultdict(dict)

    def grp(dim, key):
        if key not in groups[dim]:
            groups[dim][key] = Group(fields)
        return groups[dim][key]

    for sid, lab in labels.items():
        pred = preds.get(sid)
        hw = lab.get("is_handwritten", {})
        keys = {
            "legibility": lab["legibility"],
            "recipient_handwriting": "handwritten" if hw.get("recipient") else "printed",
            "sender_handwriting": ("none" if hw.get("sender") is None else "handwritten" if hw["sender"] else "printed"),
            "sender_type": lab["sender"]["sender_type"],
        }
        targets = [overall] + [grp(d, k) for d, k in keys.items()]
        truth_illegible = lab["legibility"] == "illegible"
        flagged = is_flagged(pred)
        rn = get_path(pred or {}, FIELDS["recipient.name"])
        guessed = rn is not MISSING and bool(norm(rn))
        for g in targets:
            g.flag.add(truth_illegible, flagged, guessed)
        if truth_illegible:
            continue  # illegible samples are scored only through the flag
        for f in fields:
            t = get_path(lab, FIELDS[f])
            p = get_path(pred or {}, FIELDS[f])
            p = None if p is MISSING else p
            for g in targets:
                g.fields[f].add(None if t is MISSING else t, p)
        if notes_present:
            for g in targets:
                g.notes.add(lab.get("notes", []), (pred or {}).get("notes") or [])

    return {
        "samples": len(labels),
        "predictions_found": len(set(preds) & set(labels)),
        "missing_predictions": len(set(labels) - set(preds)),
        "unknown_prediction_files": unknown[:20],
        "fields_evaluated": fields + (["notes"] if notes_present else []),
        "fields_not_predicted": [f for f in FIELDS if f not in present] + ([] if notes_present else ["notes"]),
        "overall": overall.report(notes_present),
        "breakdowns": {dim: {k: g.report(notes_present) for k, g in sorted(gs.items())} for dim, gs in groups.items()},
    }


# --------------------------------------------------------------------------- printing


def fmt(v, pct=True):
    if v is None:
        return "  -  "
    return f"{100 * v:5.1f}" if pct else f"{v:5d}"


def print_report(rep: dict):
    print(f"samples: {rep['samples']}   predictions: {rep['predictions_found']}   "
          f"missing predictions: {rep['missing_predictions']}")
    if rep["fields_not_predicted"]:
        print(f"not predicted (skipped): {', '.join(rep['fields_not_predicted'])}")
    if rep["unknown_prediction_files"]:
        print(f"prediction files with no matching label (ignored): {rep['unknown_prediction_files']}")

    ov = rep["overall"]
    fl = ov["illegible_flag"]
    print("\n== Illegible flag (all samples) ==")
    print(f"  precision {fmt(fl['precision'])}%   recall {fmt(fl['recall'])}%   F1 {fmt(fl['f1'])}%   "
          f"(TP {fl['tp']}  FP {fl['fp']}  FN {fl['fn']}  TN {fl['tn']})")
    print(f"  illegible samples: {fl['illegible_total']}   attempted to read instead of flagging: "
          f"{fl['illegible_attempted_not_flagged']}   (of which output a recipient name: "
          f"{fl['illegible_attempted_with_recipient_guess']})")
    print(f"  false-flag rate on readable (clear+degraded) samples: {fmt(fl['flag_rate_on_readable'])}%")

    print("\n== Field accuracy (clear + degraded samples only) ==")
    cols = rep["fields_evaluated"]
    print(f"  {'field':22s} {'n':>6s} {'EM%':>6s} {'EMstr%':>7s} {'CER%':>6s}   notes: {'P%':>6s} {'R%':>6s}")
    for f in cols:
        r = ov[f]
        if not r.get("n"):
            continue
        extra = ""
        if f == "notes":
            extra = f"          {fmt(r['note_precision'])}  {fmt(r['note_recall'])}"
        print(f"  {f:22s} {r['n']:6d} {fmt(r['em'])}  {fmt(r.get('em_strict'))}  {fmt(r['cer'])}{extra}")

    for dim, groups in rep["breakdowns"].items():
        print(f"\n== By {dim} ==  (n = all samples, n_read = clear+degraded used for field scores)")
        head = f"  {'group':14s} {'n':>5s} {'n_read':>6s}"
        for f in cols:
            short = f.replace("recipient.", "rcpt.").replace("sender.organization", "sndr.org").replace("sender.", "sndr.")
            head += f" | {short + ' EM/CER':>19s}"
        head += " | flag P/R        | flagged"
        print(head)
        for key, g in groups.items():
            fl = g["illegible_flag"]
            n_total = fl["tp"] + fl["fp"] + fl["fn"] + fl["tn"]
            n_read = fl["fp"] + fl["tn"]
            row = f"  {key:14s} {n_total:5d} {n_read:6d}"
            for f in cols:
                r = g[f]
                row += f" | {fmt(r.get('em'))} / {fmt(r.get('cer'))}    " if r.get("n") else f" | {'n/a':>19s}"
            flagged = (fl["tp"] + fl["fp"]) / n_total if n_total else None
            row += f" | {fmt(fl['precision'])} / {fmt(fl['recall'])} | {fmt(flagged)}%"
            print(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(HERE / "dataset"), help="dataset folder (or its labels/ folder)")
    ap.add_argument("--predictions", required=True, help="folder of {id}.json predictions")
    ap.add_argument("--json", help="also write the full report to this JSON file")
    args = ap.parse_args()
    rep = evaluate(Path(args.data), Path(args.predictions))
    print_report(rep)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2))
        print(f"\nfull report written to {args.json}")


if __name__ == "__main__":
    main()
