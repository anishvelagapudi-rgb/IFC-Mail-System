"""Semantic content of a mail item: sender, recipient, notes, back-of-envelope text.

Everything here is pure data (no drawing). All organization names are fictional
or generic; none are real agencies or companies, and no real logos are used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from faker import Faker

# --------------------------------------------------------------------------- helpers


def choice(rng: np.random.Generator, seq):
    return seq[int(rng.integers(len(seq)))]


def weighted(rng: np.random.Generator, weights: dict):
    keys = list(weights)
    p = np.array([float(weights[k]) for k in keys])
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def chance(rng: np.random.Generator, p: float) -> bool:
    return bool(rng.random() < p)


# --------------------------------------------------------------------------- sender pools

GOV = {
    "benefits": {
        "orgs": ["Federal Benefits Administration", "Office of Retirement & Disability Benefits",
                 "National Benefits Service Center"],
        "depts": ["Program Service Center", "Office of Central Operations", "Benefit Notices Unit"],
        "federal": True,
    },
    "tax": {
        "orgs": ["Department of Revenue", "Federal Tax Service Center", "State Revenue Office"],
        "depts": ["Notice Processing Unit", "Taxpayer Services", "Refund Processing"],
        "federal": True,
    },
    "health": {
        "orgs": ["State Department of Health Services", "Office of Medical Assistance",
                 "State Health Benefits Program"],
        "depts": ["Eligibility Services", "Member Services", "Renewals Unit"],
        "federal": False,
    },
    "dmv": {
        "orgs": ["Department of Motor Vehicles", "Division of Motor Vehicles", "Motor Vehicle Services"],
        "depts": ["Driver License Section", "Vehicle Registration", "ID Card Services"],
        "federal": False,
    },
    "court": {
        "orgs": ["County District Court", "Office of the Clerk of Superior Court", "Municipal Court"],
        "depts": ["Clerk's Office", "Criminal Division", "Civil Division", "Traffic Division"],
        "federal": False,
    },
    "housing": {
        "orgs": ["County Housing Authority", "Regional Housing Assistance Office"],
        "depts": ["Voucher Programs", "Intake & Waitlist"],
        "federal": False,
    },
    "employment": {
        "orgs": ["Division of Employment Security", "State Workforce Commission"],
        "depts": ["Unemployment Insurance", "Claims Processing"],
        "federal": False,
    },
}
GOV_WEIGHTS = {"benefits": 0.24, "tax": 0.16, "health": 0.2, "dmv": 0.12, "court": 0.14,
               "housing": 0.08, "employment": 0.06}

PLACE_WORDS = ["Heritage", "Summit", "Lakeside", "Pinewood", "Harborview", "Unity", "Riverbend",
               "Old Mill", "Bluestone", "Northgate", "Meadowbrook", "Crescent", "Tri-County",
               "Fairhaven", "Cedar Point", "Brightwater", "Granite Ridge", "Oak Hollow"]

BANK_SUFFIX = ["Community Bank", "Savings Bank", "Federal Credit Union", "Card Services",
               "Bank & Trust", "Financial", "Credit Union"]
BANK_DEPTS = ["Card Services", "Customer Care", "Collections Department", "Account Services", None, None]

HEALTH_SUFFIX = ["Medical Center", "Family Medicine", "Community Health Clinic", "Regional Hospital",
                 "Pharmacy", "Dental Associates", "Behavioral Health", "Urgent Care"]
HEALTH_DEPTS = ["Patient Billing", "Billing Department", "Patient Accounts", "Medical Records", None]

EMPLOYER_SUFFIX = ["Staffing Solutions", "Logistics", "Foods Inc.", "Building Services",
                   "Hospitality Group", "Distribution Center", "Landscaping Co.", "Warehouse LLC"]
EMPLOYER_DEPTS = ["Payroll Department", "Human Resources", "HR / Payroll", None]

JUNK_SUFFIX = ["Wireless", "Auto Insurance", "Home Warranty", "Lending Group", "Rewards Club",
               "Vacation Club", "Furniture Outlet", "Auto Sales", "Satellite TV", "Benefit Advisors"]
JUNK_DEPTS = ["Special Offers", "Member Rewards", None, None]

NC_CITIES = [("Raleigh", "276"), ("Durham", "277"), ("Greensboro", "274"), ("Charlotte", "282"),
             ("Winston-Salem", "271"), ("Fayetteville", "283"), ("Cary", "275"), ("Hillsborough", "272"),
             ("Carrboro", "275"), ("Burlington", "272"), ("Sanford", "273"), ("Wilmington", "284")]

# --------------------------------------------------------------------------- notes

ENDORSEMENTS = {
    "government": ["IMPORTANT INFORMATION ENCLOSED", "TIME SENSITIVE", "Return Service Requested",
                   "Do Not Forward", "ACTION REQUIRED", "IMPORTANT TAX DOCUMENT ENCLOSED",
                   "Address Service Requested", "RESPONSE REQUIRED BY DUE DATE", "OPEN IMMEDIATELY"],
    "bank": ["Return Service Requested", "IMPORTANT ACCOUNT INFORMATION", "Address Service Requested",
             "Do Not Forward", "TIME SENSITIVE", "Your New Card Is Enclosed", "PERSONAL & CONFIDENTIAL"],
    "healthcare": ["Return Service Requested", "PERSONAL & CONFIDENTIAL", "Change Service Requested",
                   "TIME SENSITIVE", "Statement Enclosed", "FINAL NOTICE"],
    "employer": ["IMPORTANT TAX DOCUMENT ENCLOSED", "Return Service Requested", "Payroll Information Enclosed",
                 "PERSONAL & CONFIDENTIAL", "TIME SENSITIVE"],
    "junk": ["OPEN IMMEDIATELY", "TIME SENSITIVE", "You Have Been Pre-Approved!", "Exclusive Offer Inside",
             "DATED MATERIAL - OPEN PROMPTLY", "Second Notice", "Do Not Discard", "FREE GIFT INSIDE",
             "Reply Requested Within 10 Days"],
}
RUBBER_STAMPS = ["URGENT", "SECOND NOTICE", "FINAL NOTICE", "PERSONAL", "CONFIDENTIAL", "TIME SENSITIVE",
                 "PRIORITY", "PLEASE FORWARD"]
HANDWRITTEN_NOTES_PERSONAL = ["please call me", "Please call me!", "Call me when you get this",
                              "Miss you!", "Photos - Do not bend", "Write back soon", "Urgent!",
                              "Hope you're doing ok", "Happy Birthday!", "please deliver - thank you",
                              "Hold for pickup", "Do Not Bend"]
HANDWRITTEN_NOTES_ORG = ["please call me", "Please call our office", "Urgent - please respond",
                         "Signature required", "Call 919-555-0142"]
BACK_NOTES_PERSONAL = ["Write back!", "Love you", "SWAK", "Miss you", "please call me", "xoxo",
                       "Call me!"]
BACK_PRINTED = ["Printed on recycled paper", "If undeliverable, please return to sender",
                "THIS ENVELOPE IS RECYCLABLE", "Please recycle"]

# --------------------------------------------------------------------------- names

NICKNAMES = {
    "William": ["Bill", "Will", "Billy"], "Robert": ["Bob", "Rob", "Bobby"], "Richard": ["Rick", "Dick", "Rich"],
    "James": ["Jim", "Jimmy", "Jamie"], "Michael": ["Mike", "Mikey"], "Thomas": ["Tom", "Tommy"],
    "Joseph": ["Joe", "Joey"], "Charles": ["Charlie", "Chuck"], "Christopher": ["Chris"],
    "Daniel": ["Dan", "Danny"], "Anthony": ["Tony"], "Edward": ["Ed", "Eddie"], "Kenneth": ["Ken", "Kenny"],
    "Donald": ["Don", "Donnie"], "Steven": ["Steve"], "Timothy": ["Tim"], "Gregory": ["Greg"],
    "Raymond": ["Ray"], "Lawrence": ["Larry"], "Gerald": ["Jerry"], "Douglas": ["Doug"],
    "Elizabeth": ["Liz", "Beth", "Betty", "Lizzie"], "Margaret": ["Peggy", "Maggie", "Meg"],
    "Patricia": ["Pat", "Patty", "Trish"], "Jennifer": ["Jen", "Jenny"], "Katherine": ["Kate", "Kathy", "Katie"],
    "Deborah": ["Deb", "Debbie"], "Rebecca": ["Becky"], "Susan": ["Sue", "Suzy"], "Barbara": ["Barb"],
    "Kimberly": ["Kim"], "Victoria": ["Vicky", "Tori"], "Samantha": ["Sam"], "Jessica": ["Jess"],
    "Cynthia": ["Cindy"], "Dorothy": ["Dot", "Dottie"], "Theresa": ["Terry", "Tess"],
    "Alexander": ["Alex"], "Nicholas": ["Nick"], "Benjamin": ["Ben"], "Jonathan": ["Jon"],
    "Samuel": ["Sam"], "Frederick": ["Fred"], "Leonard": ["Leo", "Lenny"], "Ronald": ["Ron", "Ronnie"],
}

PHONETIC = [("ph", "f"), ("f", "ph"), ("ie", "ei"), ("ei", "ie"), ("c", "k"), ("k", "c"), ("y", "ie"),
            ("ll", "l"), ("l", "ll"), ("tt", "t"), ("nn", "n"), ("son", "sen"), ("sen", "son"),
            ("ey", "y"), ("ck", "k"), ("ow", "ough"), ("er", "ar"), ("ia", "ya"), ("th", "t")]


def misspell(rng: np.random.Generator, word: str) -> str:
    """Return a plausible human misspelling of word (always different from word if possible)."""
    if len(word) < 3:
        return word
    lower = word.lower()
    ops = ["phonetic", "swap", "drop", "double"]
    for _ in range(8):
        op = choice(rng, ops)
        if op == "phonetic":
            cands = [(a, b) for a, b in PHONETIC if a in lower[1:]]
            if not cands:
                continue
            a, b = choice(rng, cands)
            idx = lower.index(a, 1)
            out = word[:idx] + b + word[idx + len(a):]
        elif op == "swap":
            i = int(rng.integers(1, len(word) - 1))
            out = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        elif op == "drop":
            i = int(rng.integers(1, len(word)))
            out = word[:i] + word[i + 1:]
        else:
            i = int(rng.integers(1, len(word)))
            out = word[:i] + word[i - 1] + word[i:]
        if word[0].isupper():
            out = out[0].upper() + out[1:]
        if out.lower() != lower:
            return out
    return word


# --------------------------------------------------------------------------- data classes


@dataclass
class Sender:
    sender_type: str
    sender_subtype: str | None
    name: str | None                 # a person's name, if one is printed/written
    organization: str | None
    department: str | None
    address_lines: list[str]         # street/PO box line(s) + city line
    extra_lines: list[str] = field(default_factory=list)   # e.g. "OFFICIAL BUSINESS"
    address_location: str = "front"  # front | back | both | none
    handwritten: bool = False
    uppercase: bool = False

    def block_lines(self) -> list[str]:
        """Lines exactly as printed in the return-address block."""
        lines = []
        for v in (self.name, self.organization, self.department):
            if v:
                lines.append(v)
        lines += self.address_lines
        return lines


@dataclass
class Recipient:
    name: str                        # exactly as printed
    canonical_name: str | None       # the intended person's real name (roster match target)
    name_variant: str                # exact | misspelled | nickname | current_resident
    care_of: str | None              # text after "c/o", exactly as printed
    address_lines: list[str]
    addressing: str                  # care_of | direct | name_only
    pre_lines: list[str] = field(default_factory=list)    # presort line, above the name
    post_name_lines: list[str] = field(default_factory=list)  # e.g. "OR CURRENT RESIDENT"
    handwritten: bool = False
    co_prefix: str = "c/o"

    def block_lines(self) -> list[str]:
        lines = list(self.pre_lines) + [self.name] + list(self.post_name_lines)
        if self.care_of:
            lines.append(f"{self.co_prefix} {self.care_of}")
        return lines + list(self.address_lines)


@dataclass
class Note:
    text: str
    side: str          # front | back
    style: str         # printed | rubber_stamp | handwritten
    zone: str          # layout hint: below_return | above_recipient | lower_left | anywhere | flap


@dataclass
class MailContent:
    sender: Sender
    recipient: Recipient
    notes: list[Note]
    received_at: datetime
    postmark_date: datetime | None
    postage: str                     # stamp | meter | permit
    back_printed: list[str]
    back_flap_lines: list[str]       # sender address lines written on the back flap
    back_flap_handwritten: bool
    personal_message_kind: str | None = None


# --------------------------------------------------------------------------- generators


def _street(fk: Faker, rng, upper: bool) -> str:
    s = fk.street_address()
    if chance(rng, 0.25):
        s = f"PO Box {int(rng.integers(100, 99999))}"
    return s.upper().replace(".", "") if upper else s


def _city_line(city: str, state: str, zipc: str, upper: bool, comma: bool = True) -> str:
    line = f"{city}{',' if comma else ''} {state} {zipc}"
    return line.upper() if upper else line


def _random_city(fk: Faker, rng, in_state: bool) -> tuple[str, str, str]:
    if in_state:
        city, prefix = choice(rng, NC_CITIES)
        return city, "NC", f"{prefix}{int(rng.integers(0, 100)):02d}"
    return fk.city(), fk.state_abbr(include_territories=False), fk.zipcode()


SUFFIX_ABBR = {"Lane": "Ln", "Street": "St", "Avenue": "Ave", "Road": "Rd", "Drive": "Dr", "Boulevard": "Blvd",
               "Court": "Ct", "Place": "Pl", "Circle": "Cir", "Way": "Way"}


def shelter_street(cfg_shelter: dict, rng, upper: bool) -> str:
    street = cfg_shelter["street"]
    parts = street.split()
    if parts[-1] in SUFFIX_ABBR and (upper or chance(rng, 0.4)):
        parts[-1] = SUFFIX_ABBR[parts[-1]]
    s = " ".join(parts)
    return s.upper() if upper else s


def make_sender(cfg: dict, fk: Faker, rng, sender_type: str) -> Sender:
    in_state = chance(rng, 0.6)
    subtype = None
    dept = None
    name = None
    extra: list[str] = []
    upper = False
    if sender_type == "government":
        subtype = weighted(rng, GOV_WEIGHTS)
        pool = GOV[subtype]
        org = choice(rng, pool["orgs"])
        dept = choice(rng, pool["depts"]) if chance(rng, 0.6) else None
        upper = chance(rng, 0.55)
        in_state = not pool["federal"] or chance(rng, 0.2)
        if pool["federal"] and chance(rng, 0.5):
            extra = ["OFFICIAL BUSINESS", "PENALTY FOR PRIVATE USE $300"]
    elif sender_type == "bank":
        org = f"{choice(rng, PLACE_WORDS)} {choice(rng, BANK_SUFFIX)}"
        dept = choice(rng, BANK_DEPTS)
        upper = chance(rng, 0.4)
    elif sender_type == "healthcare":
        org = f"{choice(rng, PLACE_WORDS)} {choice(rng, HEALTH_SUFFIX)}"
        dept = choice(rng, HEALTH_DEPTS)
        if chance(rng, 0.2):
            name = f"Dr. {fk.first_name()} {fk.last_name()}"
            dept = None
        in_state = chance(rng, 0.85)
    elif sender_type == "employer":
        org = f"{choice(rng, PLACE_WORDS)} {choice(rng, EMPLOYER_SUFFIX)}"
        dept = choice(rng, EMPLOYER_DEPTS)
        in_state = chance(rng, 0.8)
    elif sender_type == "junk":
        org = f"{choice(rng, PLACE_WORDS)} {choice(rng, JUNK_SUFFIX)}"
        dept = choice(rng, JUNK_DEPTS)
        upper = chance(rng, 0.5)
    elif sender_type == "personal":
        org = None
        name = f"{fk.first_name()} {fk.last_name()}" if chance(rng, 0.8) else fk.first_name()
        in_state = chance(rng, 0.5)
    else:
        raise ValueError(sender_type)

    if sender_type == "personal":
        street = fk.street_address()
        if chance(rng, 0.15):
            # mail from a family member at a facility / apartment
            street = f"{fk.building_number()} {fk.street_name()} Apt {int(rng.integers(1, 40))}"
    else:
        street = _street(fk, rng, upper)
    city, state, zipc = _random_city(fk, rng, in_state)
    if sender_type != "personal" and chance(rng, 0.3):
        zipc = f"{zipc}-{int(rng.integers(0, 10000)):04d}"
    addr = [street, _city_line(city, state, zipc, upper, comma=not upper or chance(rng, 0.5))]

    if upper:
        org = org.upper() if org else org
        dept = dept.upper() if dept else dept
        name = name.upper() if name else name
        addr = [a.upper() for a in addr]

    return Sender(sender_type, subtype, name, org, dept, addr, extra, handwritten=(sender_type == "personal"
                  and chance(rng, 0.95)), uppercase=upper)


def make_recipient(cfg: dict, fk: Faker, rng, sender: Sender, force_handwritten: bool | None) -> Recipient:
    rcfg = cfg["recipient"]
    sh = cfg["shelter"]
    personal = sender.sender_type == "personal"
    upper = sender.uppercase or (not personal and chance(rng, 0.3))

    # Canonical (intended) person.
    variant = "exact"
    use_nickname = chance(rng, rcfg["nickname_rate"])
    first = choice(rng, list(NICKNAMES)) if use_nickname else fk.first_name()
    last = fk.last_name()
    canonical = f"{first} {last}"
    middle = f" {chr(65 + int(rng.integers(26)))}" if chance(rng, rcfg["middle_initial_rate"]) else ""
    if middle and chance(rng, 0.5):
        middle += "."

    shown_first, shown_last = first, last
    if use_nickname:
        shown_first = choice(rng, NICKNAMES[first])
        variant = "nickname"
    if variant == "exact" and chance(rng, rcfg["misspelling_rate"]):
        if chance(rng, 0.6):
            shown_last = misspell(rng, last)
        else:
            shown_first = misspell(rng, first)
        if f"{shown_first} {shown_last}" != canonical:
            variant = "misspelled"

    if personal and chance(rng, 0.35):
        name = shown_first if chance(rng, 0.3) else f"{shown_first} {shown_last}"
    else:
        name = f"{shown_first}{'' if personal and chance(rng, 0.7) else middle} {shown_last}"
    if upper:
        name = name.upper()

    post_name: list[str] = []
    pre: list[str] = []
    if sender.sender_type == "junk":
        if chance(rng, rcfg["junk_current_resident_rate"]):
            if chance(rng, 0.35):
                name, canonical, variant = ("CURRENT RESIDENT" if upper or chance(rng, 0.5)
                                            else "Current Resident"), None, "current_resident"
            else:
                post_name = ["OR CURRENT RESIDENT" if upper else "Or Current Resident"]
        if chance(rng, 0.5):
            stars = "*" * int(rng.integers(8, 20))
            pre = [f"{stars}AUTO**5-DIGIT {sh['zip']}" if chance(rng, 0.6) else f"{stars}ECRWSS"]

    addressing = weighted(rng, rcfg["addressing"])
    if variant == "current_resident" and addressing == "name_only":
        addressing = "direct"
    care_of = None
    address_lines: list[str] = []
    co_prefix = "c/o"
    if addressing in ("care_of", "direct"):
        use_po = chance(rng, sh.get("po_box_rate", 0))
        if use_po:
            line1 = sh["po_box"].upper() if upper else sh["po_box"]
            zipc = sh["po_box_zip"]
        else:
            line1 = shelter_street(sh, rng, upper)
            zipc = sh["zip"]
            if not personal and sh.get("zip4") and chance(rng, 0.3):
                zipc = f"{zipc}-{sh['zip4']}"
        address_lines = [line1, _city_line(sh["city"], sh["state"], zipc, upper, comma=not upper or chance(rng, 0.5))]
    if addressing == "care_of":
        care_of = choice(rng, sh["aliases"])
        if upper:
            care_of = care_of.upper()
        co_prefix = choice(rng, ["C/O", "c/o"]) if upper else choice(rng, ["c/o", "c/o", "C/O", "care of"])
        if upper:
            co_prefix = co_prefix.upper()
    handwritten = (personal and chance(rng, 0.95)) or (not personal and chance(rng, 0.03))
    if force_handwritten is not None:
        handwritten = force_handwritten
    if handwritten:
        pre = []   # presort / "OR CURRENT RESIDENT" lines are machine-printed only
        post_name = []
    return Recipient(name, canonical, variant, care_of, address_lines, addressing, pre, post_name,
                     handwritten, co_prefix)


def random_received_at(cfg: dict, rng) -> datetime:
    rc = cfg["received_at"]
    tz = ZoneInfo(rc.get("timezone", "UTC"))
    start = datetime.fromisoformat(str(rc["start"])).replace(tzinfo=tz)
    end = datetime.fromisoformat(str(rc["end"])).replace(tzinfo=tz)
    days = max(1, (end - start).days + 1)
    hours = rc.get("business_hours")
    for _ in range(100):
        day = start + timedelta(days=int(rng.integers(days)))
        if rc.get("weekdays_only") and day.weekday() >= 5:
            continue
        lo, hi = (hours if hours else (0, 24))
        secs = int(rng.integers(int(lo * 3600), int(hi * 3600)))
        return day.replace(hour=0, minute=0, second=0) + timedelta(seconds=secs)
    return start


def make_content(cfg: dict, fk: Faker, rng, force_messy: bool = False) -> MailContent:
    if force_messy:
        # scrawled addresses come overwhelmingly from people, occasionally a hand-addressed office envelope
        sender_type = "personal" if chance(rng, 0.75) else weighted(rng, {k: v for k, v in cfg["sender_types"].items()
                                                                          if k not in ("personal", "junk")})
    else:
        sender_type = weighted(rng, cfg["sender_types"])
    sender = make_sender(cfg, fk, rng, sender_type)
    personal = sender_type == "personal"
    recipient = make_recipient(cfg, fk, rng, sender, True if force_messy else None)

    # Where is the return address?
    back_flap_lines: list[str] = []
    back_flap_hw = False
    if personal:
        sender.address_location = weighted(rng, cfg["sender_address"]["personal_location"])
    elif chance(rng, cfg["sender_address"]["org_back_flap_rate"]):
        sender.address_location = "both"
    if sender.address_location in ("back", "both"):
        back_flap_lines = sender.block_lines()
        back_flap_hw = sender.handwritten
    if sender.address_location == "none":
        sender.address_lines = []

    ncfg = cfg["notes"]
    notes: list[Note] = []
    if not personal:
        if chance(rng, ncfg["printed_endorsement_rate"]):
            pool = ENDORSEMENTS[sender_type]
            k = 1 if chance(rng, 0.75) else 2
            for t in rng.choice(len(pool), size=k, replace=False):
                notes.append(Note(pool[int(t)], "front", "printed",
                                  choice(rng, ["below_return", "below_return", "above_recipient", "lower_left"])))
        if chance(rng, ncfg["rubber_stamp_rate"]):
            notes.append(Note(choice(rng, RUBBER_STAMPS), "front", "rubber_stamp", "anywhere"))
        if chance(rng, ncfg["handwritten_note_rate_org"]):
            notes.append(Note(choice(rng, HANDWRITTEN_NOTES_ORG), "front", "handwritten", "lower_left"))
    else:
        if chance(rng, ncfg["handwritten_note_rate_personal"]):
            notes.append(Note(choice(rng, HANDWRITTEN_NOTES_PERSONAL), "front", "handwritten",
                              choice(rng, ["lower_left", "anywhere"])))
        if chance(rng, ncfg["back_note_rate_personal"]):
            notes.append(Note(choice(rng, BACK_NOTES_PERSONAL), "back", "handwritten", "flap"))

    received = random_received_at(cfg, rng)
    if personal:
        postage = "stamp"
    elif sender_type == "junk":
        postage = weighted(rng, {"permit": 0.6, "meter": 0.3, "stamp": 0.1})
    elif sender_type == "government":
        postage = weighted(rng, {"meter": 0.55, "permit": 0.4, "stamp": 0.05})
    else:
        postage = weighted(rng, {"meter": 0.65, "permit": 0.25, "stamp": 0.1})
    postmark = received - timedelta(days=int(rng.integers(1, 7))) if postage != "permit" else None

    back_printed: list[str] = []
    if not personal and chance(rng, 0.25):
        back_printed.append(choice(rng, BACK_PRINTED))

    return MailContent(sender, recipient, notes, received, postmark, postage, back_printed,
                       back_flap_lines, back_flap_hw)
