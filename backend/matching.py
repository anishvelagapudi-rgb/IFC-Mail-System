"""Match a recipient name read off an envelope to a member of the org.

Order-insensitive exact match against the member's name and aliases (same rule as the web
app's store.matchMember), then a strict fuzzy fallback that only accepts a single clear winner.
Anything else returns None and the item stays unassigned for staff to pick.
"""
import re
from difflib import SequenceMatcher

FUZZY_MIN = 0.90   # similarity required for a fuzzy match
FUZZY_GAP = 0.08   # best must beat the runner-up (a different member) by this much


def norm(name) -> str:
    words = re.sub(r"[^a-z\s]", " ", (name or "").lower()).split()
    return " ".join(sorted(words))


def match(name: str, members: list[dict]) -> dict | None:
    n = norm(name)
    if not n:
        return None
    exact = [m for m in members if any(norm(x) == n for x in [m["name"], *(m.get("aliases") or [])])]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # two members share this name: a person must decide

    scored = []
    for m in members:
        best = max((SequenceMatcher(None, n, norm(x)).ratio() for x in [m["name"], *(m.get("aliases") or [])] if norm(x)), default=0)
        scored.append((best, m))
    scored.sort(key=lambda t: t[0], reverse=True)
    if not scored or scored[0][0] < FUZZY_MIN:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_GAP:
        return None
    return scored[0][1]
