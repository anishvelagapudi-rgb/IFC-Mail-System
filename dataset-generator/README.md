# Synthetic shelter-mail dataset generator

Generates photographed-envelope images (front + back) with ground-truth labels, for
measuring a pipeline that reads incoming mail at a shelter: who it's from, who it's for,
any notes on the envelope, and whether it is too illegible to read (and should be flagged
for a person instead of guessed).

All senders, people and addresses are synthetic. Organization names are fictional or
generic ("Department of Revenue", "Summit Community Bank"); logos are simple procedural
shapes, and stamps / meter marks are procedurally drawn. The shelter address in
`config.yaml` is a fictional street in Chapel Hill, NC.

Everything for the dataset lives in this `dataset-generator/` folder. The scripts resolve
their default paths (fonts, config, output) relative to this folder, so they also work
when run from elsewhere, e.g. `python dataset-generator/generate.py` from the repo root.

## Setup (Ubuntu)

```bash
cd dataset-generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup_fonts.py          # downloads 14 OFL fonts into fonts/
```

`setup_fonts.py` downloads from the `google/fonts` GitHub repo **pinned to commit
`bbda7253fc363238b05d97515ca71f8ae49c4fa9`**, so setup is reproducible. It also saves each
font's `OFL.txt` license into `fonts/licenses/` and writes `fonts/fonts.json` (file,
category, source URL, sha256).

| category | fonts | used for |
|---|---|---|
| handwriting | Caveat, Reenie Beanie, Nothing You Could Do, Indie Flower, Shadows Into Light | personal letters, handwritten notes |
| messy | Zeyada, La Belle Aurore | the "extremely messy handwriting" illegible case |
| mono | Courier Prime, Roboto Mono, IBM Plex Mono | printed / typewriter addresses |
| print | Open Sans, Lato, Libre Baskerville | printed addresses, endorsements |

Homemade Apple was dropped from the suggested list: in google/fonts it is
Apache-2.0-licensed, not OFL.

## Usage

From inside `dataset-generator/`:

```bash
# small preview
python generate.py --count 20 --seed 42 --out dataset/ --overwrite

# full dataset
python generate.py --count 5000 --seed 42 --out dataset/ --illegible-rate 0.1 --augment-strength medium

# draw the label boxes on a few samples to check them visually -> dataset/debug/
python debug_boxes.py --data dataset/ --n 10
python debug_boxes.py --data dataset/ --legibility illegible --n 10

# score a pipeline
python evaluate.py --data dataset/ --predictions my_predictions/ --json report.json
```

`generate.py` options:

| flag | default | meaning |
|---|---|---|
| `--count` | 100 | number of mail items |
| `--seed` | 42 | master seed |
| `--out` | `dataset-generator/dataset` | output folder (refuses to overwrite unless `--overwrite`) |
| `--illegible-rate` | config (0.10) | probability a sample is deliberately illegible |
| `--augment-strength` | `medium` | `none` \| `light` \| `medium` \| `heavy` (presets in `config.yaml`) |
| `--workers` | CPU count | worker processes |
| `--start-index` | 0 | first sample index, for generating shards on several machines |
| `--config` | `dataset-generator/config.yaml` | alternate config |

**Determinism.** Each sample gets its own RNG streams derived from `(seed, index)`, so sample
`i` comes out byte-for-byte the same no matter the worker count or `--count`. For example,
the first 20 samples of a 5,000-sample run match a 20-sample run with the same seed. As a
result `--illegible-rate` is a per-sample probability, so 5,000 samples gives about 500
illegible ones, not exactly 500.

**Speed.** About 3.4 samples/s on a 6-core laptop i3-1215U, so 5,000 samples take
about 25 minutes. Each sample is two 1600×1200 JPEGs.

## Output

```
dataset-generator/dataset/
  images/   {id}_front.jpg, {id}_back.jpg
  labels/   {id}.json
  manifest.csv          one row per sample, key fields
  dataset_info.json     seed, counts, timing
  config_used.yaml      the exact config used
  debug/                (only if you run debug_boxes.py)
```

### Label JSON

```jsonc
{
  "id": "mail_000003",
  "sender": {
    "name": null,                         // a person's name if one is printed/written, else null
    "organization": "DEPARTMENT OF MOTOR VEHICLES",
    "department": "ID CARD SERVICES",
    "address_lines": ["PO BOX 17835", "FAYETTEVILLE, NC 28358"],
    "sender_type": "government",          // government | bank | healthcare | employer | personal | junk
    "sender_subtype": "dmv",              // government only: benefits | tax | health | dmv | court | housing | employment
    "address_location": "both",           // front | back | both | none (no return address anywhere)
    "raw_lines_front": [...],             // every line of the front return-address block, as printed
    "raw_lines_back":  [...]              // lines written/printed on the back flap
  },
  "recipient": {
    "name": "DOT H BRIGGS",               // exactly as printed (may be misspelled / nickname)
    "canonical_name": "Dorothy Briggs",   // the intended person (for roster matching); null for "Current Resident"
    "name_variant": "nickname",           // exact | misspelled | nickname | current_resident
    "care_of": "HLCS",                    // text after "c/o" / "care of", else null
    "address_lines": ["PO BOX 2391", "CHAPEL HILL, NC 27515"],
    "addressing": "care_of",              // care_of | direct | name_only
    "raw_lines": [...]                    // the whole block, incl. presort lines like "***AUTO**5-DIGIT 27516"
  },
  "notes": ["IMPORTANT INFORMATION ENCLOSED", "Return Service Requested"],   // exactly as they appear, front then back
  "notes_detail": [{"text": "...", "side": "front", "style": "printed|rubber_stamp|handwritten", "box": "note_0"}],
  "received_at": "2026-07-13T10:38:06-04:00",   // simulated intake time, NOT printed on the envelope
  "postmark_date": "2026-07-09",                 // printed in the postmark / meter (null for permit mail)
  "is_handwritten": {"sender": false, "recipient": false},   // sender is null when there is no return address
  "legibility": "degraded",              // clear | degraded | illegible
  "illegible_reason": null,              // heavy_blur | water_damage | smudge | sticker_cover | overlapping_envelope | messy_handwriting | extreme_low_light
  "degraded_by": ["defocus_blur"],       // which thresholds made a readable sample "degraded"
  "envelope": {"size": "#10", "color": "white", "window": false, "postage": "permit", ...},
  "augmentations_applied": [{"side": "front", "name": "perspective", "params": {...}}, ...],
  "boxes": {
    "front": {"recipient": {...}, "sender": {...}, "stamp": {...}, "note_0": {...}, ...},
    "back":  {"sender": {...}, "note_1": {...}, "seal": {...}, ...}
  }
}
```

**Boxes.** Every box has:
- `polygon`: the element's 4 corners in final-image pixels, exact under rotation and perspective. Corners can lie outside the image when the photo is partially cropped.
- `bbox`: `[x0, y0, x1, y1]`, the axis-aligned box around the polygon, clipped to the image.
- `visibility`: the fraction of the polygon inside the frame.
- `occluded_fraction`: only present when a sticker or another envelope covers the element.

Required keys: `recipient` (always on the front), `sender` (on each side where the return address appears), `stamp` (front), and one `note_k` per note, where `k` is that note's index in `notes`. Extra keys when present: `postmark`, `logo`, `window`, `barcode`, `address_label`, `sender_extra` ("OFFICIAL BUSINESS / PENALTY FOR PRIVATE USE"), `occluder`, `damage`, and on the back `seal`, `clasp`, `back_text`, `id_tag`.

**Legibility.**
- `illegible`: deliberately made unreadable (`illegible_reason` says how). The full ground truth is still recorded, so you can see what the pipeline should have flagged.
- `degraded`: still readable by a careful human, but crosses a `degraded_thresholds` value in the config: blur, noise, low light, heavy JPEG, a strong cast shadow, or small text. Random blur on non-illegible samples is capped relative to the recipient text's size in the photo, so "degraded" never quietly means unreadable.
- `clear`: everything else.
- The label describes the front photo. The back photo is a separate shot with its own augmentations.

## Content mix (all configurable in `config.yaml`)

- **Recipients:** about 58% "Name / c/o Shelter / address", 28% "Name / shelter address", and 14% name only. The c/o line uses shelter aliases ("Harbor Light", "HLCS"). About 10% of addressed items use the shelter PO box. Misspellings (phonetic, swapped, dropped or doubled letters) run about 12%, nicknames (Bill for William, Dot for Dorothy) about 10%, and junk mail adds "Or Current Resident" and presort lines.
- **Senders:** government (benefits, tax, state health/Medicaid-style, DMV, courts, housing, unemployment), banks and card issuers, healthcare providers, employers, personal letters (about 95% handwritten), and junk mail.
- **Notes:** USPS-style endorsements ("Return Service Requested", "Do Not Forward"), "TIME SENSITIVE" / "OPEN IMMEDIATELY", red rubber stamps ("URGENT", "FINAL NOTICE"), and handwritten notes ("please call me") on the front or the back flap.
- **Envelopes:** #10 business (often with an address window), #6¾, A7 card, 6×9, 9×12 and 10×13 manila or kraft with a clasp. Paper comes in several colors. Postage is a stamp with a postmark, a meter mark, or a permit imprint. Some items carry an Intelligent-Mail-style barcode.
- **Backs:** flap styles, tape or sticker seals, a printed or handwritten return address on the flap, small printed text, and USPS-style ID-tag bars.
- **Photo effects:** a cluttered or textured background (wood, laminate, fabric, papers, pens, coffee rings), a drop shadow, rotation, 3-D camera tilt, partial cropping, uneven lighting, hand or phone shadows, low light with white-balance shift, defocus and motion blur, sensor noise, and JPEG re-compression.

## Evaluation

`evaluate.py` reads a predictions folder of `{id}.json` files, using the same shape as the labels, with any subset of fields. It scores:

- `recipient.name`, `sender.name` and `sender.organization` on exact match (case- and whitespace-insensitive, plus a strict variant) and character error rate.
- `notes` as an unordered list: exact match of the whole set, CER after pairing each predicted note with its closest true note, and note-level precision and recall.
- The illegible flag (`"legibility": "illegible"` or `"illegible": true`) on precision, recall and F1, plus how many illegible samples the pipeline tried to read instead of flagging, and how many of those produced a recipient-name guess.

**Field accuracy only counts samples whose true legibility is `clear` or `degraded`.** Illegible samples are scored only through the flag. Results are broken down by legibility, recipient handwritten vs. printed, sender handwritten vs. printed vs. none, and sender_type.

A sample with no prediction file counts as "not flagged" with empty fields. A field missing from every prediction file is reported as "not predicted" and skipped.

## Folder layout

```
dataset-generator/
config.yaml          all tunables (shelter address, mixes, augmentation presets, thresholds)
setup_fonts.py       pinned font download
generate.py          CLI, multiprocessing, manifest
evaluate.py          scoring
debug_boxes.py       box overlay visualizer
mailgen/
  content.py         sender / recipient / notes generation (pure data)
  text.py            printed, typewriter, handwriting, rubber-stamp text rendering
  envelope.py        front/back layout and drawing; records each element's box
  degrade.py         illegible damage: water stain, smudge, sticker, overlapping envelope
  background.py      procedural backgrounds
  augment.py         phone-photo geometry (single homography) + photometric effects
  sample.py          one sample end-to-end, label JSON, manifest row
  noise.py           fast deterministic noise tiles
  fonts.py, config.py
```

**How the boxes stay correct.** Elements are drawn on a flat envelope, and each one's rectangle is recorded from the ink actually pasted. All the photo geometry (placement, rotation, camera tilt, crop) is one 3×3 homography `H`. The image is warped with `cv2.warpPerspective(H)`, and every box corner goes through `cv2.perspectiveTransform(H)`, so the two use exactly the same mapping. Every effect after the warp is photometric and moves no pixels.
