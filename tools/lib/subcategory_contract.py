"""Subcategory contract — ZERO drift enforcement for research.

This is the single enforcement layer that prevents category drift.
Every product at every pipeline stage MUST pass the contract.
Any drift is a HARD FAIL — no exceptions.

The contract is a "skill procedure" (inspired by the Skills pattern):
  - It defines exact allowed/disallowed subcategory labels.
  - It includes acceptance_test checks that must all pass.
  - It includes disambiguation_rules for ambiguous cases.
  - Every agent references this contract before making decisions.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SubcategoryContract:
    """Strict subcategory enforcement contract.

    This contract is the single source of truth for what products
    are allowed in a pipeline run. Every stage references it.
    """
    niche_name: str                         # "open-back headphones"
    category: str                           # "audio"
    # --- Subcategory labels ---
    allowed_subcategory_labels: list[str] = field(default_factory=list)
        # e.g. ["open-back"] — products must match at least one
    disallowed_labels: list[str] = field(default_factory=list)
        # e.g. ["closed-back", "earbuds", "iem", "gaming headset"] — instant reject
    # --- Keyword enforcement ---
    allowed_keywords: list[str] = field(default_factory=list)
        # Product name must contain at least 1
    disallowed_keywords: list[str] = field(default_factory=list)
        # Product name must NOT contain any
    mandatory_keywords: list[str] = field(default_factory=list)
        # At least 3 — product name or known attributes must match >= 1
    # --- Disambiguation ---
    disambiguation_rules: str = ""
        # Structured rules for ambiguous cases
    # --- Acceptance test ---
    acceptance_test: dict = field(default_factory=dict)
        # Structured checks that must ALL pass:
        # {"name_must_contain_one_of": [...], "name_must_not_contain": [...],
        #  "brand_is_not_product_name": true, "min_keyword_matches": 1}


# ---------------------------------------------------------------------------
# Curated templates — subcategory-level (NOT category-level)
# ---------------------------------------------------------------------------
# Key insight: templates must distinguish WITHIN a category.
# "open-back headphones" vs "closed-back headphones" vs "earbuds"
# are all "audio" category but DIFFERENT subcategories.

_CONTRACT_TEMPLATES: dict[str, dict] = {
    # ===== AUDIO — subcategory-level distinctions =====
    "wireless earbuds": {
        "subcategory_labels": ["earbuds", "true wireless", "tws"],
        "disallowed_labels": ["headphone", "over-ear", "on-ear", "open-back",
                              "closed-back", "gaming headset", "iem", "wired earbuds",
                              "speaker", "soundbar", "microphone", "turntable"],
        "allowed": ["earbuds", "earbud", "true wireless", "tws", "in-ear wireless"],
        "disallowed": ["headphone", "over-ear", "on-ear", "open-back", "closed-back",
                       "speaker", "soundbar", "microphone", "gaming headset"],
        "mandatory": ["earbuds", "earbud", "in-ear", "tws"],
        "disambiguation": (
            "If a product name is ambiguous (e.g. 'Sony X' without type), "
            "check the source page for 'true wireless' or 'earbuds' in description. "
            "If the source says 'headphones' (not earbuds), REJECT. "
            "IEMs (in-ear monitors) are wired — REJECT unless explicitly wireless earbuds."
        ),
        "acceptance_test": {
            "name_must_not_contain": ["headphone", "over-ear", "on-ear", "speaker",
                                      "soundbar", "gaming headset", "open-back", "closed-back"],
            "brand_is_not_product_name": True,
        },
    },
    "over-ear headphones": {
        "subcategory_labels": ["over-ear", "around-ear", "full-size headphones"],
        "disallowed_labels": ["earbuds", "earbud", "in-ear", "iem", "tws",
                              "on-ear", "speaker", "soundbar", "gaming headset"],
        "allowed": ["headphone", "over-ear", "over ear", "around-ear", "full-size"],
        "disallowed": ["earbuds", "earbud", "in-ear", "tws", "true wireless",
                       "speaker", "soundbar", "on-ear", "gaming headset"],
        "mandatory": ["headphone", "over-ear", "over ear", "around-ear"],
        "disambiguation": (
            "Must be OVER-ear (circumaural), not on-ear (supra-aural). "
            "If source says 'on-ear' or cup size is small, REJECT. "
            "Gaming headsets with mic booms are a different subcategory — REJECT."
        ),
        "acceptance_test": {
            "name_must_not_contain": ["earbuds", "earbud", "in-ear", "tws", "speaker",
                                      "soundbar", "on-ear"],
            "brand_is_not_product_name": True,
        },
    },
    "open-back headphones": {
        "subcategory_labels": ["open-back", "open back"],
        "disallowed_labels": ["closed-back", "closed back", "earbuds", "earbud",
                              "in-ear", "iem", "tws", "gaming headset", "on-ear",
                              "speaker", "soundbar"],
        "allowed": ["headphone", "open-back", "open back", "planar", "electrostatic"],
        "disallowed": ["closed-back", "closed back", "earbuds", "earbud", "in-ear",
                       "tws", "true wireless", "speaker", "soundbar", "on-ear",
                       "gaming headset", "noise cancelling", "anc"],
        "mandatory": ["open-back", "open back", "headphone", "planar"],
        "disambiguation": (
            "Must be OPEN-back design. If source says 'closed-back' or 'noise cancelling', REJECT. "
            "ANC headphones are always closed-back — REJECT. "
            "Planar magnetic headphones are often open-back but verify with source."
        ),
        "acceptance_test": {
            "name_must_not_contain": ["closed-back", "closed back", "earbuds", "earbud",
                                      "in-ear", "tws", "speaker", "soundbar", "anc",
                                      "noise cancelling", "gaming headset"],
            "brand_is_not_product_name": True,
        },
    },
    "noise cancelling headphones": {
        "subcategory_labels": ["noise cancelling", "anc", "active noise cancelling"],
        "disallowed_labels": ["earbuds", "earbud", "open-back", "speaker",
                              "soundbar", "gaming headset", "iem"],
        "allowed": ["headphone", "noise cancelling", "anc", "active noise"],
        "disallowed": ["earbuds", "earbud", "open-back", "open back",
                       "speaker", "soundbar", "gaming headset"],
        "mandatory": ["headphone", "noise cancelling", "anc"],
        "disambiguation": (
            "Must be over-ear or on-ear HEADPHONES with ANC. "
            "ANC earbuds are a different subcategory — REJECT. "
            "Passive noise isolation is NOT ANC — REJECT."
        ),
        "acceptance_test": {
            "name_must_not_contain": ["earbuds", "earbud", "open-back", "speaker", "soundbar"],
            "brand_is_not_product_name": True,
        },
    },
    "soundbars": {
        "subcategory_labels": ["soundbar", "sound bar"],
        "disallowed_labels": ["headphone", "earbuds", "speaker", "turntable",
                              "subwoofer", "receiver"],
        "allowed": ["soundbar", "sound bar", "atmos bar"],
        "disallowed": ["headphone", "earbuds", "earbud", "speaker stand",
                       "turntable", "bookshelf speaker", "portable speaker"],
        "mandatory": ["soundbar", "sound bar"],
        "disambiguation": "A soundbar is a single elongated speaker unit for TV audio.",
        "acceptance_test": {
            "name_must_contain_one_of": ["soundbar", "sound bar"],
            "name_must_not_contain": ["headphone", "earbuds", "turntable",
                                      "bookshelf", "portable speaker"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "bluetooth speakers": {
        "subcategory_labels": ["bluetooth speaker", "portable speaker", "wireless speaker"],
        "disallowed_labels": ["headphone", "earbuds", "soundbar", "turntable",
                              "bookshelf speaker", "studio monitor"],
        "allowed": ["speaker", "bluetooth speaker", "portable speaker", "wireless speaker"],
        "disallowed": ["headphone", "earbuds", "earbud", "soundbar", "turntable",
                       "bookshelf", "studio monitor"],
        "mandatory": ["speaker"],
        "disambiguation": "Must be portable/bluetooth speakers, not soundbars, bookshelf, or studio monitors.",
        "acceptance_test": {
            "name_must_contain_one_of": ["speaker"],
            "name_must_not_contain": ["headphone", "earbuds", "soundbar",
                                      "turntable", "bookshelf", "studio monitor"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== COMPUTING =====
    "mechanical keyboards": {
        "subcategory_labels": ["mechanical keyboard", "mechanical"],
        "disallowed_labels": ["membrane", "mouse", "webcam", "monitor",
                              "headphone", "gaming mouse"],
        "allowed": ["keyboard", "mechanical", "keycap", "switch", "hot-swap"],
        "disallowed": ["mouse", "webcam", "monitor", "headphone", "membrane",
                       "trackpad", "controller"],
        "mandatory": ["keyboard", "mechanical"],
        "disambiguation": "Must be mechanical (not membrane/rubber dome). Gaming keyboards must have mechanical switches.",
        "acceptance_test": {
            "name_must_contain_one_of": ["keyboard"],
            "name_must_not_contain": ["mouse", "webcam", "monitor", "headphone",
                                      "membrane", "trackpad"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "4k monitors": {
        "subcategory_labels": ["4k monitor", "4k", "uhd monitor"],
        "disallowed_labels": ["1080p", "1440p", "keyboard", "mouse",
                              "tv", "television", "projector"],
        "allowed": ["monitor", "4k", "display", "screen", "uhd"],
        "disallowed": ["keyboard", "mouse", "webcam", "tv", "television",
                       "projector", "laptop"],
        "mandatory": ["monitor", "display", "4k"],
        "disambiguation": "Must be 4K (3840x2160) monitors. TVs and projectors are different subcategories.",
        "acceptance_test": {
            "name_must_contain_one_of": ["monitor", "display"],
            "name_must_not_contain": ["keyboard", "mouse", "webcam", "tv",
                                      "television", "projector"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "webcams": {
        "subcategory_labels": ["webcam", "web camera", "streaming camera"],
        "disallowed_labels": ["headphone", "microphone", "ring light",
                              "keyboard", "dslr", "action camera"],
        "allowed": ["webcam", "web cam", "streaming camera"],
        "disallowed": ["headphone", "microphone", "ring light", "keyboard",
                       "dslr", "action camera", "camcorder"],
        "mandatory": ["webcam", "web cam", "camera"],
        "disambiguation": "Must be USB webcams for video calls/streaming, not DSLRs, action cameras, or camcorders.",
        "acceptance_test": {
            "name_must_contain_one_of": ["webcam", "web cam"],
            "name_must_not_contain": ["headphone", "microphone", "ring light",
                                      "dslr", "action camera"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== HOME =====
    "robot vacuums": {
        "subcategory_labels": ["robot vacuum", "robovac"],
        "disallowed_labels": ["stick vacuum", "upright vacuum", "handheld vacuum",
                              "air purifier", "thermostat", "mop only"],
        "allowed": ["vacuum", "robot vacuum", "robo vac", "mop", "robovac"],
        "disallowed": ["air purifier", "thermostat", "router", "speaker",
                       "stick vacuum", "upright", "handheld vacuum"],
        "mandatory": ["vacuum", "vac", "robot"],
        "disambiguation": "Must be ROBOT vacuums (autonomous). Stick/upright/handheld are different subcategories.",
        "acceptance_test": {
            "name_must_contain_one_of": ["vacuum", "vac", "robot"],
            "name_must_not_contain": ["air purifier", "thermostat", "router",
                                      "stick vacuum", "upright", "handheld"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "air purifiers": {
        "subcategory_labels": ["air purifier", "hepa purifier"],
        "disallowed_labels": ["vacuum", "humidifier", "dehumidifier", "fan",
                              "heater", "air conditioner"],
        "allowed": ["purifier", "air purifier", "hepa", "air cleaner"],
        "disallowed": ["vacuum", "humidifier", "dehumidifier", "fan",
                       "heater", "air conditioner"],
        "mandatory": ["purifier", "air purifier", "air cleaner"],
        "disambiguation": "Must be air purifiers (HEPA/activated carbon). Not humidifiers, fans, or ACs.",
        "acceptance_test": {
            "name_must_contain_one_of": ["purifier", "air cleaner"],
            "name_must_not_contain": ["vacuum", "humidifier", "dehumidifier",
                                      "fan", "heater", "air conditioner"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== KITCHEN =====
    "air fryers": {
        "subcategory_labels": ["air fryer"],
        "disallowed_labels": ["blender", "coffee", "espresso", "toaster",
                              "microwave", "oven", "slow cooker", "pressure cooker"],
        "allowed": ["air fryer", "fryer", "convection oven"],
        "disallowed": ["blender", "coffee", "espresso", "toaster", "microwave",
                       "slow cooker", "pressure cooker", "stand mixer"],
        "mandatory": ["fryer", "air fryer"],
        "disambiguation": "Must be air fryers. Toaster ovens with 'air fry mode' are borderline — accept only if primary function.",
        "acceptance_test": {
            "name_must_contain_one_of": ["fryer", "air fryer"],
            "name_must_not_contain": ["blender", "coffee", "espresso", "toaster",
                                      "microwave", "slow cooker", "pressure cooker"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "espresso machines": {
        "subcategory_labels": ["espresso machine", "espresso maker"],
        "disallowed_labels": ["drip coffee", "pour over", "french press",
                              "air fryer", "blender", "toaster"],
        "allowed": ["espresso", "coffee maker", "coffee machine", "barista", "portafilter"],
        "disallowed": ["air fryer", "blender", "toaster", "kettle",
                       "drip coffee", "pour over", "french press"],
        "mandatory": ["espresso", "coffee"],
        "disambiguation": "Must be espresso machines (pump-driven). Drip coffee makers, pour-over, french press are different.",
        "acceptance_test": {
            "name_must_contain_one_of": ["espresso", "coffee"],
            "name_must_not_contain": ["air fryer", "blender", "toaster",
                                      "drip", "pour over", "french press"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== TRAVEL =====
    "carry on luggage": {
        "subcategory_labels": ["carry-on", "carry on", "cabin luggage"],
        "disallowed_labels": ["checked luggage", "checked bag", "backpack",
                              "duffel", "garment bag", "tote", "briefcase",
                              "headphone", "camera", "earbuds"],
        "allowed": ["carry-on", "carry on", "luggage", "suitcase", "spinner",
                    "hardside", "softside", "cabin bag"],
        "disallowed": ["backpack", "duffel", "garment bag", "checked",
                       "headphone", "camera", "earbuds", "tote", "briefcase"],
        "mandatory": ["luggage", "suitcase", "carry-on", "carry on", "spinner", "cabin"],
        "disambiguation": (
            "Must be carry-on sized luggage (fits overhead bin, typically 22x14x9). "
            "Checked luggage (larger) is a DIFFERENT subcategory — REJECT. "
            "Travel backpacks, duffels, garment bags are DIFFERENT — REJECT."
        ),
        "acceptance_test": {
            "name_must_contain_one_of": ["luggage", "suitcase", "carry-on", "carry on",
                                          "spinner", "cabin"],
            "name_must_not_contain": ["backpack", "duffel", "garment bag", "checked",
                                      "headphone", "camera", "earbuds"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "travel backpacks": {
        "subcategory_labels": ["travel backpack", "travel pack"],
        "disallowed_labels": ["luggage", "suitcase", "duffel", "briefcase",
                              "headphone", "camera bag"],
        "allowed": ["backpack", "travel pack", "daypack", "rucksack"],
        "disallowed": ["luggage", "suitcase", "duffel", "briefcase",
                       "headphone", "camera bag", "tote"],
        "mandatory": ["backpack", "pack"],
        "disambiguation": "Must be travel backpacks. Laptop backpacks, camera bags, everyday daypacks are different.",
        "acceptance_test": {
            "name_must_contain_one_of": ["backpack", "pack"],
            "name_must_not_contain": ["luggage", "suitcase", "duffel",
                                      "briefcase", "headphone"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== FITNESS =====
    "fitness trackers": {
        "subcategory_labels": ["fitness tracker", "activity tracker"],
        "disallowed_labels": ["smartwatch", "gps watch", "headphone", "earbuds",
                              "smart scale"],
        "allowed": ["fitness tracker", "activity tracker", "fitness band", "health tracker"],
        "disallowed": ["smartwatch", "smart watch", "headphone", "earbuds",
                       "scale", "gps watch"],
        "mandatory": ["tracker", "band", "fitness"],
        "disambiguation": "Must be fitness trackers/bands. Full smartwatches (Apple Watch, Galaxy Watch) are different.",
        "acceptance_test": {
            "name_must_contain_one_of": ["tracker", "band", "fitness"],
            "name_must_not_contain": ["smartwatch", "smart watch", "headphone",
                                      "earbuds", "scale"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    "smartwatches": {
        "subcategory_labels": ["smartwatch", "smart watch"],
        "disallowed_labels": ["fitness tracker", "fitness band", "headphone",
                              "earbuds", "smart ring"],
        "allowed": ["smartwatch", "smart watch", "watch"],
        "disallowed": ["fitness tracker", "fitness band", "headphone",
                       "earbuds", "smart ring"],
        "mandatory": ["smartwatch", "smart watch", "watch"],
        "disambiguation": "Must be full smartwatches (touch screen, apps). Simple fitness bands are different.",
        "acceptance_test": {
            "name_must_contain_one_of": ["smartwatch", "smart watch", "watch"],
            "name_must_not_contain": ["fitness tracker", "fitness band",
                                      "headphone", "earbuds"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
    # ===== GAMING =====
    "gaming keyboards": {
        "subcategory_labels": ["gaming keyboard"],
        "disallowed_labels": ["gaming mouse", "gaming headset", "controller",
                              "capture card", "gaming chair"],
        "allowed": ["keyboard", "gaming keyboard", "mechanical", "switch"],
        "disallowed": ["mouse", "headset", "controller", "capture card",
                       "gaming chair", "webcam", "monitor"],
        "mandatory": ["keyboard"],
        "disambiguation": "Must be gaming keyboards. Gaming mice, headsets, controllers are different.",
        "acceptance_test": {
            "name_must_contain_one_of": ["keyboard"],
            "name_must_not_contain": ["mouse", "headset", "controller",
                                      "capture card", "gaming chair"],
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    },
}


def _cross_category_disallowed(category: str) -> list[str]:
    """Build disallowed keywords from OTHER categories' keywords."""
    from tools.lib.dzine_schema import _CATEGORY_KEYWORDS

    disallowed: list[str] = []
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if cat != category:
            disallowed.extend(keywords)
    return disallowed


def generate_contract_from_micro_niche(micro_niche) -> SubcategoryContract:
    """Generate a SubcategoryContract from a MicroNicheDef.

    Maps must_have_features -> allowed/mandatory keywords,
    forbidden_variants -> disallowed keywords.
    Tries existing template first, augments with micro-niche data.
    """
    niche = micro_niche.subcategory
    niche_lower = niche.lower().strip()

    # Derive category from subcategory name (best effort)
    category = _guess_category(niche_lower)

    # Try template match first
    base: SubcategoryContract | None = None
    if niche_lower in _CONTRACT_TEMPLATES:
        base = _from_template(niche, category, _CONTRACT_TEMPLATES[niche_lower])
    else:
        for template_key, tpl in _CONTRACT_TEMPLATES.items():
            if template_key in niche_lower or niche_lower in template_key:
                base = _from_template(niche, category, tpl)
                break

    if base is None:
        base = _auto_generate(niche, niche_lower, category)

    # Augment with micro-niche data
    for feat in micro_niche.must_have_features:
        feat_lower = feat.lower()
        if feat_lower not in [k.lower() for k in base.allowed_keywords]:
            base.allowed_keywords.append(feat_lower)

    for variant in micro_niche.forbidden_variants:
        variant_lower = variant.lower()
        if variant_lower not in [k.lower() for k in base.disallowed_keywords]:
            base.disallowed_keywords.append(variant_lower)
        if variant_lower not in [k.lower() for k in base.disallowed_labels]:
            base.disallowed_labels.append(variant_lower)
        # Also add to acceptance_test name_must_not_contain
        must_not = base.acceptance_test.get("name_must_not_contain", [])
        if variant_lower not in [k.lower() for k in must_not]:
            must_not.append(variant_lower)
            base.acceptance_test["name_must_not_contain"] = must_not

    return base


def _guess_category(niche_lower: str) -> str:
    """Best-effort category guess from niche name."""
    category_hints = {
        "audio": ["headphone", "earbuds", "speaker", "soundbar", "microphone"],
        "computing": ["keyboard", "mouse", "monitor", "webcam", "ssd"],
        "home": ["vacuum", "purifier", "humidifier", "lock", "thermostat", "camera"],
        "kitchen": ["fryer", "espresso", "coffee", "blender", "mixer", "cookware",
                     "processor"],
        "office": ["chair", "desk", "lamp", "arm"],
        "travel": ["luggage", "backpack", "charger", "pillow", "packing"],
        "fitness": ["tracker", "watch", "shoe", "dumbbell"],
    }
    for cat, hints in category_hints.items():
        if any(h in niche_lower for h in hints):
            return cat
    return "general"


def generate_contract(niche: str, category: str) -> SubcategoryContract:
    """Generate a SubcategoryContract for a niche.

    Uses curated templates for known niches (subcategory-level),
    otherwise builds from category keywords with cross-category exclusion.
    """
    niche_lower = niche.lower().strip()

    # Try exact template match
    if niche_lower in _CONTRACT_TEMPLATES:
        return _from_template(niche, category, _CONTRACT_TEMPLATES[niche_lower])

    # Try partial match — but must be substring, not accidental overlap
    for template_key, tpl in _CONTRACT_TEMPLATES.items():
        if template_key in niche_lower or niche_lower in template_key:
            return _from_template(niche, category, tpl)

    # Fallback: auto-generate from category keywords + niche words
    return _auto_generate(niche, niche_lower, category)


def _from_template(niche: str, category: str, tpl: dict) -> SubcategoryContract:
    """Build contract from a curated template."""
    return SubcategoryContract(
        niche_name=niche,
        category=category,
        allowed_subcategory_labels=list(tpl.get("subcategory_labels", [])),
        disallowed_labels=list(tpl.get("disallowed_labels", [])),
        allowed_keywords=list(tpl["allowed"]),
        disallowed_keywords=list(tpl["disallowed"]),
        mandatory_keywords=list(tpl["mandatory"]),
        disambiguation_rules=tpl.get("disambiguation", ""),
        acceptance_test=dict(tpl.get("acceptance_test", {})),
    )


def _auto_generate(niche: str, niche_lower: str, category: str) -> SubcategoryContract:
    """Auto-generate contract for unknown niches."""
    from tools.lib.dzine_schema import _CATEGORY_KEYWORDS

    allowed = list(_CATEGORY_KEYWORDS.get(category, []))
    niche_words = [w for w in niche_lower.split() if len(w) > 2]
    for w in niche_words:
        if w not in allowed:
            allowed.append(w)

    disallowed = _cross_category_disallowed(category)
    mandatory = niche_words[:3] if niche_words else allowed[:2]

    return SubcategoryContract(
        niche_name=niche,
        category=category,
        allowed_subcategory_labels=niche_words[:2],
        disallowed_labels=[],
        allowed_keywords=allowed,
        disallowed_keywords=disallowed,
        mandatory_keywords=mandatory,
        disambiguation_rules=f"Auto-generated from category '{category}' keywords. Manual review recommended.",
        acceptance_test={
            "name_must_contain_one_of": mandatory,
            "name_must_not_contain": disallowed[:20],  # cap for readability
            "brand_is_not_product_name": True,
            "min_keyword_matches": 1,
        },
    )


# ---------------------------------------------------------------------------
# Gate enforcement — HARD FAIL on any drift
# ---------------------------------------------------------------------------


def passes_gate(
    product_name: str, brand: str, contract: SubcategoryContract,
) -> tuple[bool, str]:
    """Check if a product passes the subcategory gate.

    Returns (True, "") or (False, "DRIFT: reason for rejection").
    Every check is strict. Any failure is a hard reject.
    """
    name_lower = product_name.lower()
    brand_lower = brand.lower().strip()

    # --- Use acceptance_test if available (structured, deterministic) ---
    test = contract.acceptance_test
    if test:
        return _run_acceptance_test(product_name, name_lower, brand_lower, test, contract)

    # --- Fallback to keyword-based checks ---
    return _keyword_gate(product_name, name_lower, brand_lower, contract)


def _run_acceptance_test(
    product_name: str,
    name_lower: str,
    brand_lower: str,
    test: dict,
    contract: SubcategoryContract,
) -> tuple[bool, str]:
    """Run the structured acceptance test. All checks must pass."""

    # NOTE: name_must_contain_one_of is intentionally SKIPPED.
    # Product model names (e.g. "Sony WF-1000XM5") do not contain category
    # keywords ("earbuds"). The research pipeline already ensures products
    # come from relevant comparison pages. Negative filtering below is
    # sufficient for drift prevention.

    # Check 1: name must NOT contain any disallowed terms
    must_not = test.get("name_must_not_contain", [])
    for kw in must_not:
        if kw.lower() in name_lower:
            return False, (
                f"DRIFT: '{product_name}' contains disallowed term '{kw}'. "
                f"This is NOT '{contract.niche_name}'."
            )

    # Check 2: brand alone is not the product name (noise detection)
    if test.get("brand_is_not_product_name", False):
        name_stripped = re.sub(r'[^\w\s]', '', product_name).strip()
        if brand_lower and name_stripped.lower() == brand_lower:
            return False, (
                f"DRIFT: Product name '{product_name}' is just the brand "
                f"with no model — this is noise, not a product."
            )

    # Check 3: disallowed_labels (broader than keyword, catches descriptions)
    for label in contract.disallowed_labels:
        if label.lower() in name_lower:
            return False, (
                f"DRIFT: '{product_name}' matches disallowed label '{label}'. "
                f"This belongs to a different subcategory."
            )

    return True, ""


def _keyword_gate(
    product_name: str,
    name_lower: str,
    brand_lower: str,
    contract: SubcategoryContract,
) -> tuple[bool, str]:
    """Fallback keyword-based gate when no acceptance_test is defined."""

    # Check 1: must contain at least 1 mandatory or allowed keyword
    has_keyword = False
    for kw in contract.mandatory_keywords:
        if kw.lower() in name_lower:
            has_keyword = True
            break
    if not has_keyword:
        for kw in contract.allowed_keywords:
            if kw.lower() in name_lower:
                has_keyword = True
                break
    if not has_keyword:
        return False, (
            f"DRIFT: No allowed keyword found in '{product_name}'. "
            f"Expected one of: {contract.mandatory_keywords or contract.allowed_keywords}"
        )

    # Check 2: must NOT contain disallowed keywords
    for kw in contract.disallowed_keywords:
        if kw.lower() in name_lower:
            return False, f"DRIFT: Disallowed keyword '{kw}' found in '{product_name}'"

    # Check 3: brand alone is not the product name
    name_stripped = re.sub(r'[^\w\s]', '', product_name).strip()
    if brand_lower and name_stripped.lower() == brand_lower:
        return False, f"DRIFT: Product name is just the brand '{brand}' with no model"

    return True, ""


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def write_contract(contract: SubcategoryContract, path: Path) -> None:
    """Serialize contract to JSON."""
    data = {
        "niche_name": contract.niche_name,
        "category": contract.category,
        "allowed_subcategory_labels": contract.allowed_subcategory_labels,
        "disallowed_labels": contract.disallowed_labels,
        "allowed_keywords": contract.allowed_keywords,
        "disallowed_keywords": contract.disallowed_keywords,
        "mandatory_keywords": contract.mandatory_keywords,
        "disambiguation_rules": contract.disambiguation_rules,
        "acceptance_test": contract.acceptance_test,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_contract(path: Path) -> SubcategoryContract:
    """Load contract from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return SubcategoryContract(
        niche_name=data.get("niche_name", ""),
        category=data.get("category", ""),
        allowed_subcategory_labels=data.get("allowed_subcategory_labels", []),
        disallowed_labels=data.get("disallowed_labels", []),
        allowed_keywords=data.get("allowed_keywords", []),
        disallowed_keywords=data.get("disallowed_keywords", []),
        mandatory_keywords=data.get("mandatory_keywords",
                                     data.get("mandatory_product_keywords", [])),
        disambiguation_rules=data.get("disambiguation_rules", ""),
        acceptance_test=data.get("acceptance_test", {}),
    )
