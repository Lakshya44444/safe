"""Small campus helper bot: complaints, "which bin does this go in?", and Bhawan scores.

Deliberately rule-based, not an LLM: every answer comes from a fixed sorting table or from
the app's own data, so it cannot invent a rule or a number. When it doesn't know, it says so.
The conversation state (e.g. "waiting for the Bhawan name") travels in `context`, so the
server stays stateless.
"""

from __future__ import annotations

import re

from . import config, db, scoring
from .matching import BHAWAN_HI, ISSUE_ALIASES

# What goes where, per the four SWM Rules 2026 streams. Only unambiguous everyday items;
# anything not listed gets "I'm not sure" rather than a guess. Longest phrase wins.
ITEMS: dict[str, str] = {}
for stream, words in {
    "wet": ["food", "leftover", "leftovers", "rice", "roti", "chapati", "dal", "sabzi", "vegetable", "vegetables",
            "fruit", "fruits", "peel", "peels", "banana", "banana peel", "orange peel", "tea leaves", "tea bag",
            "egg shell", "eggshell", "egg shells", "flowers", "leaves", "coffee grounds", "bones",
            "khana", "chawal", "chilka", "chilke", "kela", "chai patti", "anda", "phool", "patte",
            "खाना", "चावल", "रोटी", "दाल", "सब्ज़ी", "सब्जी", "फल", "छिलका", "छिलके", "केला", "चाय पत्ती", "अंडे", "फूल", "पत्ते"],
    "dry": ["plastic", "plastic bottle", "bottle", "bottles", "paper", "newspaper", "cardboard", "carton", "box",
            "cans", "tin can", "metal", "glass", "wrapper", "wrappers", "chips packet", "packet", "polythene",
            "plastic bag", "bag", "paper cup", "cup", "straw", "tetra pak", "foil", "thermocol", "cloth",
            "botal", "kagaz", "kaagaz", "akhbar", "gatta", "thaili", "panni", "kaanch", "kapda",
            "प्लास्टिक", "बोतल", "कागज़", "कागज", "अख़बार", "अखबार", "गत्ता", "पन्नी", "थैली", "कांच", "रैपर", "पैकेट"],
    "sanitary": ["diaper", "diapers", "sanitary pad", "sanitary pads", "pad", "pads", "sanitary napkin", "napkin",
                 "tampon", "tampons", "condom", "condoms", "bandage", "bandages",
                 "डायपर", "पैड", "सैनिटरी पैड"],
    "special_care": ["battery", "batteries", "cell", "bulb", "bulbs", "tube light", "tubelight", "cfl",
                     "medicine", "medicines", "expired medicine", "tablets", "syringe", "syringes", "needle",
                     "injection", "paint", "thermometer", "pesticide", "charger", "cartridge", "chemical",
                     "dawai", "dawa", "बैटरी", "बल्ब", "दवाई", "दवा", "सिरिंज", "पेंट"],
}.items():
    for w in words:
        ITEMS[w] = stream
_ITEM_KEYS = sorted(ITEMS, key=len, reverse=True)

_COMPLAINT_WORDS = [w for w, _ in ISSUE_ALIASES] + [
    "overflowing", "bhara", "bhar gaya", "bhar gya", "full ho", "smell", "badbu", "not emptied", "complaint",
    "complain", "shikayat", "बदबू", "भर गया", "भरा", "शिकायत", "टूटा", "गाड़ी नहीं"]
_SCORE_WORDS = ["score", "rank", "grade", "how is", "how's", "kaisa", "kaise", "position", "report card", "स्कोर", "रैंक"]
_TOP_WORDS = ["top", "best", "first", "winner", "leading", "sabse accha", "सबसे अच्छा"]
_WORST_WORDS = ["worst", "last", "bottom", "sabse kharab", "सबसे खराब"]
_WHERE_WORDS = ["where", "which bin", "what bin", "kaha", "kahan", "kidhar", "kis dabbe", "kis dibbe", "kaunse",
                "kaun se", "goes", "throw", "daalu", "dalu", "daalein", "कहाँ", "कहां", "किस डब्बे"]

T = {
    "en": {
        "help": "I can log a complaint (\"bin is full at Govind\"), tell you which bin something goes in "
                "(\"where does a battery go?\"), or give a Bhawan's score (\"Ganga score\").",
        "ask_bhawan": "Which Bhawan is the bin at?",
        "logged": "Logged: {label} at {b}. Complaint #{id}. The collection team sees it on the notice board now.",
        "item": "{item} goes in the {stream} bin. That bin is for {contents}.",
        "item_special": " Never put it in the wet or dry bin.",
        "item_unknown": "I'm not sure about that item, so I won't guess. If in doubt, ask the sanitation staff. "
                        "The bins are: wet (food), dry (plastic, paper, metal, glass), sanitary (diapers, pads) "
                        "and special care (batteries, bulbs, medicines).",
        "score": "{b} scores {score}/100 this week (grade {grade}), rank {rank} of {n}, from {reports} checked bins.",
        "score_tip": " Most common wrong items: {items}.",
        "no_score": "There are no checks for {b} this week yet.",
        "top": "{b} leads this week with {score}/100.",
        "worst": "{b} is last this week with {score}/100.",
        "no_data": "No bins have been checked this week yet.",
        "status": "Complaint #{id} at {b} ({label}) is {status}.",
        "no_issue": "I can't find complaint #{id}.",
        "labels": {"overflow": "bin is full", "missed_pickup": "pickup missed", "broken_bin": "bin is broken",
                   "other": "complaint"},
        "streams": {"wet": "wet (green)", "dry": "dry (blue)", "sanitary": "sanitary", "special_care": "special care"},
        "open": "still open", "resolved": "fixed",
    },
    "hi": {
        "help": "मैं शिकायत दर्ज कर सकता हूँ (\"गोविंद में डब्बा भर गया\"), बता सकता हूँ कि कौन सी चीज़ किस डब्बे में "
                "जाती है (\"बैटरी कहाँ डालें?\"), या किसी भवन का स्कोर बता सकता हूँ (\"गंगा स्कोर\")।",
        "ask_bhawan": "डब्बा किस भवन में है?",
        "logged": "दर्ज हो गया: {b} में {label}। शिकायत #{id}। सफ़ाई टीम को नोटिस बोर्ड पर अभी दिख रहा है।",
        "item": "{item} {stream} डब्बे में जाता है। यह डब्बा {contents} के लिए है।",
        "item_special": " इसे गीले या सूखे डब्बे में कभी न डालें।",
        "item_unknown": "इस चीज़ के बारे में मुझे पक्का नहीं पता, इसलिए अंदाज़ा नहीं लगाऊँगा। सफ़ाई कर्मचारी से पूछ लें। "
                        "डब्बे: गीला (खाना), सूखा (प्लास्टिक, कागज़, धातु, कांच), सैनिटरी (डायपर, पैड), "
                        "स्पेशल केयर (बैटरी, बल्ब, दवाइयाँ)।",
        "score": "{b} का इस हफ़्ते स्कोर {score}/100 है (ग्रेड {grade}), {n} में रैंक {rank}, {reports} डब्बे जाँचे गए।",
        "score_tip": " सबसे आम गलत चीज़ें: {items}।",
        "no_score": "{b} के लिए इस हफ़्ते अभी कोई जाँच नहीं हुई।",
        "top": "इस हफ़्ते {b} {score}/100 के साथ सबसे आगे है।",
        "worst": "इस हफ़्ते {b} {score}/100 के साथ सबसे पीछे है।",
        "no_data": "इस हफ़्ते अभी कोई डब्बा नहीं जाँचा गया।",
        "status": "शिकायत #{id} ({b}, {label}): {status}।",
        "no_issue": "शिकायत #{id} नहीं मिली।",
        "labels": {"overflow": "डब्बा भर गया", "missed_pickup": "कूड़ा नहीं उठा", "broken_bin": "डब्बा टूटा है",
                   "other": "शिकायत"},
        "streams": {"wet": "गीले (हरे)", "dry": "सूखे (नीले)", "sanitary": "सैनिटरी", "special_care": "स्पेशल केयर"},
        "open": "अभी खुली है", "resolved": "ठीक हो गई",
    },
}
CONTENTS_HI = {"wet": "खाना, छिलके और चाय पत्ती", "dry": "प्लास्टिक, कागज़, धातु और कांच",
               "sanitary": "डायपर और सैनिटरी पैड", "special_care": "दवाइयाँ, बल्ब, बैटरी और पेंट"}


def _has(text: str, words: list[str]) -> bool:
    return any(_contains(text, w) for w in words)


def _contains(text: str, phrase: str) -> bool:
    if re.search(r"[ऀ-ॿ]", phrase):  # Devanagari: no \b word boundaries
        return phrase in text
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def find_bhawan(text: str) -> str | None:
    """Exact Bhawan name anywhere in a sentence (English or Hindi). No prefix guessing here."""
    for hi, en in BHAWAN_HI.items():
        if hi in text:
            return en
    for b in sorted(config.BHAWANS, key=len, reverse=True):
        if _contains(text, b.lower()):
            return b
    return None


def find_item(text: str) -> str | None:
    for k in _ITEM_KEYS:
        if _contains(text, k):
            return k
    return None


def _kind(text: str) -> str:
    for word, kind in ISSUE_ALIASES:
        if _contains(text, word):
            return kind
    if _has(text, ["bhara", "bhar gaya", "bhar gya", "overflowing", "full ho", "भर गया", "भरा"]):
        return "overflow"
    if _has(text, ["टूटा"]):
        return "broken_bin"
    if _has(text, ["गाड़ी नहीं", "not emptied"]):
        return "missed_pickup"
    return "other"


def _complaint(kind: str, bhawan: str, note: str, lang: str) -> dict:
    s = T[lang]
    iid = db.create_issue(bhawan, kind, note[:200] or None, "student (chat)")
    return {"say": s["logged"].format(label=s["labels"][kind], b=bhawan, id=iid), "issue_id": iid,
            "action": "issue_created", "context": None, "choices": []}


def reply(message: str, lang: str = "en", context: dict | None = None) -> dict:
    lang = "hi" if lang == "hi" else "en"
    s = T[lang]
    text = " ".join((message or "").lower().split())[:500]
    ctx = context or {}
    out = {"say": "", "choices": [], "context": None, "action": None}

    # Second turn of a complaint: we asked which Bhawan.
    if ctx.get("want") == "complaint_bhawan":
        b = find_bhawan(text)
        if b:
            return _complaint(ctx.get("kind", "other"), b, ctx.get("note", ""), lang)
        if not _has(text, _SCORE_WORDS + _WHERE_WORDS) and not find_item(text):
            return {**out, "say": s["ask_bhawan"], "choices": config.BHAWANS, "context": ctx}

    # Complaint status: "status 12", "complaint #12".
    m = re.search(r"(?:status|#)\s*(\d{1,7})", text)
    if m:
        iid = int(m.group(1))
        row = next((i for i in db.list_issues(None, limit=5000) if i["id"] == iid), None)
        if not row:
            return {**out, "say": s["no_issue"].format(id=iid)}
        return {**out, "say": s["status"].format(id=iid, b=row["bhawan"], label=s["labels"].get(row["kind"], row["kind"]),
                                                 status=s["resolved"] if row["status"] == "resolved" else s["open"])}

    item = find_item(text)
    wants_where = _has(text, _WHERE_WORDS)

    # Complaint: "bin is full at Govind", "pickup missed", "dabba bhar gaya".
    if _has(text, _COMPLAINT_WORDS) and not (wants_where and item):
        kind = _kind(text)
        b = find_bhawan(text)
        if b:
            return _complaint(kind, b, message.strip(), lang)
        return {**out, "say": s["ask_bhawan"], "choices": config.BHAWANS,
                "context": {"want": "complaint_bhawan", "kind": kind, "note": message.strip()[:200]}}

    # Which bin: "where does a battery go?", "kela kahan daalu".
    if item and (wants_where or len(text.split()) <= 3):
        stream = ITEMS[item]
        contents = CONTENTS_HI[stream] if lang == "hi" else config.STREAM_CONTENTS[stream]
        say = s["item"].format(item=item.capitalize() if lang == "en" else item, stream=s["streams"][stream], contents=contents)
        if stream == "special_care":
            say += s["item_special"]
        return {**out, "say": say, "action": "item", "stream": stream}
    if wants_where:
        return {**out, "say": s["item_unknown"]}

    # Scores.
    rows = scoring.bhawan_scores(7)
    b = find_bhawan(text)
    if b and (_has(text, _SCORE_WORDS) or len(text.split()) <= 2):
        row = next((r for r in rows if r["bhawan"] == b), None)
        if not row:
            return {**out, "say": s["no_score"].format(b=b)}
        say = s["score"].format(b=b, score=row["score"], grade=_grade(row["score"]), rank=row["rank"], n=len(rows),
                                reports=row["reports"])
        if row["top_wrong_items"]:
            say += s["score_tip"].format(items=", ".join(row["top_wrong_items"]))
        return {**out, "say": say}
    if _has(text, _TOP_WORDS + _WORST_WORDS):
        if not rows:
            return {**out, "say": s["no_data"]}
        worst = _has(text, _WORST_WORDS)
        row = rows[-1] if worst else rows[0]
        return {**out, "say": s["worst" if worst else "top"].format(b=row["bhawan"], score=row["score"])}

    return {**out, "say": s["help"]}


def _grade(score: int) -> str:
    return "A" if score >= 80 else "B" if score >= 60 else "C"
