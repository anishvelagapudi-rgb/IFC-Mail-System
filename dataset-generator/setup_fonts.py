#!/usr/bin/env python3
"""Download the OFL-licensed Google Fonts used by the generator into ./fonts.

URLs are pinned to a specific google/fonts commit so setup is reproducible.
Each font's OFL.txt license is downloaded alongside it.

    python setup_fonts.py            # download missing fonts
    python setup_fonts.py --force    # re-download everything
"""
import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

GOOGLE_FONTS_COMMIT = "bbda7253fc363238b05d97515ca71f8ae49c4fa9"
RAW = f"https://raw.githubusercontent.com/google/fonts/{GOOGLE_FONTS_COMMIT}/"

# (family dir in google/fonts, ttf filename, style category)
#   handwriting  - normal handwriting used for personal letters / notes
#   messy        - very hard-to-read scripts, used mostly for illegible samples
#   print        - sans/serif printed text
#   mono         - typewriter / monospace printed text
HERE = Path(__file__).resolve().parent

FONTS = [
    ("ofl/caveat", "Caveat[wght].ttf", "handwriting"),
    ("ofl/reeniebeanie", "ReenieBeanie.ttf", "handwriting"),
    ("ofl/nothingyoucoulddo", "NothingYouCouldDo.ttf", "handwriting"),
    ("ofl/indieflower", "IndieFlower-Regular.ttf", "handwriting"),
    ("ofl/shadowsintolight", "ShadowsIntoLight.ttf", "handwriting"),
    ("ofl/zeyada", "Zeyada.ttf", "messy"),
    ("ofl/labelleaurore", "LaBelleAurore.ttf", "messy"),
    ("ofl/courierprime", "CourierPrime-Regular.ttf", "mono"),
    ("ofl/robotomono", "RobotoMono[wght].ttf", "mono"),
    ("ofl/ibmplexmono", "IBMPlexMono-Regular.ttf", "mono"),
    ("ofl/opensans", "OpenSans[wdth,wght].ttf", "print"),
    ("ofl/lato", "Lato-Regular.ttf", "print"),
    ("ofl/lato", "Lato-Bold.ttf", "print_bold"),
    ("ofl/librebaskerville", "LibreBaskerville[wght].ttf", "print"),
]


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "ifc-mailgen-setup"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest.write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=str(HERE / "fonts"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    dest = Path(args.dest)
    (dest / "licenses").mkdir(parents=True, exist_ok=True)
    manifest = {"google_fonts_commit": GOOGLE_FONTS_COMMIT, "fonts": []}

    for family_dir, fname, category in FONTS:
        out = dest / fname
        url = RAW + family_dir + "/" + urllib.parse.quote(fname)
        if args.force or not out.exists():
            print(f"downloading {fname} ...")
            fetch(url, out)
        lic_out = dest / "licenses" / f"{Path(family_dir).name}_OFL.txt"
        if args.force or not lic_out.exists():
            fetch(RAW + family_dir + "/OFL.txt", lic_out)
        manifest["fonts"].append({
            "file": fname,
            "category": category,
            "source": url,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "license": "OFL-1.1",
        })

    (dest / "fonts.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(FONTS)} fonts ready in {dest}/ (google/fonts @ {GOOGLE_FONTS_COMMIT[:10]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
