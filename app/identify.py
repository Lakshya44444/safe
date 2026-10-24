"""What each identified item is, which bin it belongs in, and whether it is dangerous.

The model names the wrong items it sees. This module maps each name to its correct stream
with the same fixed sorting table the helper chat uses (no second model call, no guessing),
and flags hazards: items that can hurt the person sorting the waste, start a fire, or
poison the compost. Unknown items are kept with belongs=None rather than guessed.
"""

from __future__ import annotations

import re

from .chat import ITEMS, find_item

# keyword -> why it is dangerous. Checked before the stream rule, so sharps are flagged anywhere.
HAZARDS: list[tuple[str, str]] = [
    ("syringe", "sharps: can prick the person sorting the waste"),
    ("needle", "sharps: can prick the person sorting the waste"),
    ("injection", "sharps: can prick the person sorting the waste"),
    ("blade", "sharps: can cut the person sorting the waste"),
    ("razor", "sharps: can cut the person sorting the waste"),
    ("broken glass", "sharps: can cut the person sorting the waste"),
    ("battery", "can catch fire when crushed in the collection truck"),
    ("batteries", "can catch fire when crushed in the collection truck"),
    ("cell", "can catch fire when crushed in the collection truck"),
    ("cfl", "contains mercury"),
    ("tube light", "contains mercury"),
    ("tubelight", "contains mercury"),
    ("thermometer", "may contain mercury"),
    ("bulb", "breaks into sharp glass; CFL bulbs contain mercury"),
    ("medicine", "drugs leach into compost and soil"),
    ("tablet", "drugs leach into compost and soil"),
    ("paint", "toxic chemicals"),
    ("pesticide", "toxic chemicals"),
    ("chemical", "toxic chemicals"),
    ("diaper", "infection risk for the person sorting; spoils compost"),
    ("sanitary pad", "infection risk for the person sorting; spoils compost"),
    ("pad", "infection risk for the person sorting; spoils compost"),
    ("napkin", "infection risk for the person sorting; spoils compost"),
    ("condom", "infection risk for the person sorting; spoils compost"),
    ("bandage", "infection risk for the person sorting; spoils compost"),
]
# Hazards that are fine in their own bin (a battery in the special care bin is correct).
_SAFE_IN = {"special_care": {"syringe", "needle", "injection", "battery", "batteries", "cell", "cfl", "tube light",
                             "tubelight", "thermometer", "bulb", "medicine", "tablet", "paint", "pesticide", "chemical"},
            "sanitary": {"diaper", "sanitary pad", "pad", "napkin", "condom", "bandage"}}


def _hazard(name: str, bin_stream: str) -> str | None:
    for word, why in HAZARDS:
        if re.search(rf"(?<![a-z]){re.escape(word)}", name):
            return None if word in _SAFE_IN.get(bin_stream, set()) else why
    return None


def identify(found_items: list[str], bin_stream: str) -> list[dict]:
    out = []
    for raw in found_items or []:
        name = " ".join(str(raw).lower().split())
        key = find_item(name)
        belongs = ITEMS.get(key) if key else None
        why = _hazard(name, bin_stream)
        out.append({"item": raw, "belongs": belongs, "right_bin": belongs == bin_stream,
                    "hazard": why is not None, "why": why})
    return out


def has_hazard(found_items: list[str], bin_stream: str) -> bool:
    return any(_hazard(" ".join(str(i).lower().split()), bin_stream) for i in found_items or [])
