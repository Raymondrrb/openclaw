#!/usr/bin/env python3
"""Daily niche selection — non-repeating, scored, deterministic.

Maintains data/niche_history.json to avoid repeats within 60 days.
Picks from a curated pool of ~90 niches scored by monetization potential,
review coverage, and Amazon inventory depth.

Usage:
    python3 tools/niche_picker.py
    python3 tools/niche_picker.py --date 2026-02-11
    python3 tools/niche_picker.py --list          # show available niches
    python3 tools/niche_picker.py --history        # show recent picks

Stdlib only — no external deps.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import project_root

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = project_root() / "data"
HISTORY_PATH = DATA_DIR / "niche_history.json"
EXCLUSION_DAYS = 60

# ---------------------------------------------------------------------------
# Niche pool — curated, scored
# ---------------------------------------------------------------------------
# Fields: keyword, category, price_min, price_max, review_coverage (1-5),
#   amazon_depth (1-5), monetization (1-5)
# review_coverage: how many trusted outlets typically cover "best <niche>"
# amazon_depth: how many plausible items exist on Amazon
# monetization: typical commission-relevant price range


@dataclass
class NicheCandidate:
    keyword: str
    category: str
    subcategory: str = ""              # e.g., "true wireless earbuds"
    intent: str = ""                   # "general"|"gaming"|"travel"|"fitness"|"work"|"creative"
    price_band: str = ""               # "budget"|"mid"|"premium" (auto-derived if empty)
    buyer_intent: str = ""             # "first-time"|"upgrade"|"gift"|"replacement"
    price_min: int = 30
    price_max: int = 300
    review_coverage: int = 3   # 1-5 scale
    amazon_depth: int = 3      # 1-5 scale
    monetization: int = 3      # 1-5 scale

    def __post_init__(self):
        if not self.subcategory:
            self.subcategory = self.keyword
        if not self.intent:
            self.intent = "general"
        if not self.price_band:
            self.price_band = (
                "budget" if self.price_max < 80
                else "mid" if self.price_max < 250
                else "premium"
            )

    @property
    def score(self) -> float:
        return (
            self.review_coverage * 2.0
            + self.amazon_depth * 1.5
            + self.monetization * 2.5
        )


# ~90 curated niches, organized by category
NICHE_POOL: list[NicheCandidate] = [
    # Audio
    NicheCandidate("wireless earbuds", "audio", subcategory="true wireless earbuds", intent="general", price_band="mid", price_min=20, price_max=350, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("over-ear headphones", "audio", subcategory="over-ear headphones", intent="general", price_band="premium", price_min=50, price_max=500, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("noise cancelling headphones", "audio", subcategory="active noise cancelling headphones", intent="travel", price_band="premium", price_min=80, price_max=450, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("portable bluetooth speakers", "audio", subcategory="portable bluetooth speakers", intent="general", price_band="mid", price_min=30, price_max=300, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("soundbars", "audio", subcategory="soundbars", intent="general", price_band="premium", price_min=80, price_max=500, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("studio monitors", "audio", subcategory="studio monitors", intent="creative", price_band="premium", price_min=100, price_max=500, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("podcast microphones", "audio", subcategory="podcast microphones", intent="creative", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("USB microphones", "audio", subcategory="USB condenser microphones", intent="creative", price_band="mid", price_min=40, price_max=250, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("gaming headsets", "audio", subcategory="gaming headsets", intent="gaming", price_band="mid", price_min=40, price_max=300, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("turntables", "audio", subcategory="turntables", intent="general", price_band="premium", price_min=80, price_max=500, review_coverage=4, amazon_depth=3, monetization=4),
    NicheCandidate("bookshelf speakers", "audio", subcategory="bookshelf speakers", intent="general", price_band="premium", price_min=80, price_max=500, review_coverage=4, amazon_depth=4, monetization=4),

    # Computing / peripherals
    NicheCandidate("mechanical keyboards", "computing", subcategory="mechanical keyboards", intent="general", price_band="mid", price_min=50, price_max=300, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("ergonomic keyboards", "computing", subcategory="ergonomic keyboards", intent="work", price_band="mid", price_min=50, price_max=250, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("wireless mice", "computing", subcategory="wireless mice", intent="work", price_band="mid", price_min=30, price_max=150, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("gaming mice", "computing", subcategory="gaming mice", intent="gaming", price_band="mid", price_min=30, price_max=180, review_coverage=5, amazon_depth=5, monetization=3),
    NicheCandidate("webcams", "computing", subcategory="webcams", intent="work", price_band="mid", price_min=40, price_max=200, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("USB-C hubs", "computing", subcategory="USB-C docking stations", intent="work", price_band="budget", price_min=25, price_max=100, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("external SSDs", "computing", subcategory="portable external SSDs", intent="general", price_band="mid", price_min=50, price_max=250, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("portable monitors", "computing", subcategory="portable monitors", intent="work", price_band="mid", price_min=100, price_max=400, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("laptop stands", "computing", subcategory="laptop stands", intent="work", price_band="budget", price_min=20, price_max=80, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("computer monitors 27 inch", "computing", subcategory="27-inch monitors", intent="work", price_band="premium", price_min=150, price_max=600, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("4K monitors", "computing", subcategory="4K UHD monitors", intent="creative", price_band="premium", price_min=200, price_max=700, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("gaming monitors", "computing", subcategory="gaming monitors", intent="gaming", price_band="premium", price_min=150, price_max=600, review_coverage=5, amazon_depth=5, monetization=5),

    # Home
    NicheCandidate("robot vacuums", "home", subcategory="robot vacuums", intent="general", price_band="premium", price_min=150, price_max=800, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("air purifiers", "home", subcategory="air purifiers", intent="general", price_band="mid", price_min=50, price_max=400, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("humidifiers", "home", subcategory="humidifiers", intent="general", price_band="mid", price_min=30, price_max=150, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("dehumidifiers", "home", subcategory="dehumidifiers", intent="general", price_band="mid", price_min=100, price_max=350, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("space heaters", "home", subcategory="space heaters", intent="general", price_band="mid", price_min=30, price_max=150, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("smart thermostats", "home", subcategory="smart thermostats", intent="general", price_band="mid", price_min=80, price_max=300, review_coverage=4, amazon_depth=3, monetization=4),
    NicheCandidate("smart locks", "home", subcategory="smart locks", intent="general", price_band="mid", price_min=80, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("video doorbells", "home", subcategory="video doorbells", intent="general", price_band="mid", price_min=50, price_max=250, review_coverage=5, amazon_depth=4, monetization=4),
    NicheCandidate("mesh wifi routers", "home", subcategory="mesh wifi systems", intent="general", price_band="mid", price_min=100, price_max=400, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("wifi routers", "home", subcategory="wifi routers", intent="general", price_band="mid", price_min=50, price_max=350, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("smart plugs", "home", subcategory="smart plugs", intent="general", price_band="budget", price_min=10, price_max=50, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("smart light bulbs", "home", subcategory="smart light bulbs", intent="general", price_band="budget", price_min=10, price_max=60, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("electric toothbrushes", "home", subcategory="electric toothbrushes", intent="general", price_band="mid", price_min=30, price_max=200, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("electric shavers", "home", subcategory="electric shavers", intent="general", price_band="mid", price_min=40, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("hair clippers", "home", subcategory="hair clippers", intent="general", price_band="budget", price_min=20, price_max=100, review_coverage=3, amazon_depth=4, monetization=3),

    # Kitchen
    NicheCandidate("air fryers", "kitchen", subcategory="air fryers", intent="general", price_band="mid", price_min=40, price_max=200, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("espresso machines", "kitchen", subcategory="espresso machines", intent="general", price_band="premium", price_min=100, price_max=600, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("coffee grinders", "kitchen", subcategory="coffee grinders", intent="general", price_band="mid", price_min=30, price_max=200, review_coverage=4, amazon_depth=4, monetization=3),
    NicheCandidate("drip coffee makers", "kitchen", subcategory="drip coffee makers", intent="general", price_band="mid", price_min=30, price_max=200, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("blenders", "kitchen", subcategory="blenders", intent="general", price_band="mid", price_min=30, price_max=250, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("stand mixers", "kitchen", subcategory="stand mixers", intent="general", price_band="premium", price_min=100, price_max=500, review_coverage=4, amazon_depth=3, monetization=5),
    NicheCandidate("food processors", "kitchen", subcategory="food processors", intent="general", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("instant pots", "kitchen", subcategory="multi-cookers", intent="general", price_band="mid", price_min=50, price_max=150, review_coverage=4, amazon_depth=4, monetization=3),
    NicheCandidate("toaster ovens", "kitchen", subcategory="toaster ovens", intent="general", price_band="mid", price_min=40, price_max=250, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("electric kettles", "kitchen", subcategory="electric kettles", intent="general", price_band="budget", price_min=20, price_max=100, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("sous vide machines", "kitchen", subcategory="sous vide cookers", intent="general", price_band="mid", price_min=50, price_max=250, review_coverage=3, amazon_depth=4, monetization=4),
    NicheCandidate("knife sets", "kitchen", subcategory="kitchen knife sets", intent="general", price_band="mid", price_min=40, price_max=300, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("cast iron skillets", "kitchen", subcategory="cast iron skillets", intent="general", price_band="budget", price_min=20, price_max=100, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("nonstick cookware sets", "kitchen", subcategory="nonstick cookware sets", intent="general", price_band="mid", price_min=50, price_max=250, review_coverage=4, amazon_depth=5, monetization=4),

    # Office / desk
    NicheCandidate("standing desks", "office", subcategory="standing desks", intent="work", price_band="premium", price_min=200, price_max=700, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("office chairs", "office", subcategory="office chairs", intent="work", price_band="premium", price_min=100, price_max=500, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("ergonomic office chairs", "office", subcategory="ergonomic office chairs", intent="work", price_band="premium", price_min=200, price_max=800, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("desk lamps", "office", subcategory="desk lamps", intent="work", price_band="budget", price_min=20, price_max=100, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("monitor arms", "office", subcategory="monitor arms", intent="work", price_band="mid", price_min=30, price_max=150, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("desk organizers", "office", subcategory="desk organizers", intent="work", price_band="budget", price_min=15, price_max=60, review_coverage=2, amazon_depth=5, monetization=2),

    # Fitness / outdoor
    NicheCandidate("fitness trackers", "fitness", subcategory="fitness trackers", intent="fitness", price_band="mid", price_min=30, price_max=200, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("smartwatches", "fitness", subcategory="smartwatches", intent="fitness", price_band="premium", price_min=100, price_max=500, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("running shoes", "fitness", subcategory="running shoes", intent="fitness", price_band="mid", price_min=80, price_max=200, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("yoga mats", "fitness", subcategory="yoga mats", intent="fitness", price_band="budget", price_min=15, price_max=80, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("resistance bands", "fitness", subcategory="resistance bands", intent="fitness", price_band="budget", price_min=10, price_max=50, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("adjustable dumbbells", "fitness", subcategory="adjustable dumbbells", intent="fitness", price_band="premium", price_min=100, price_max=500, review_coverage=4, amazon_depth=3, monetization=5),
    NicheCandidate("home gym equipment", "fitness", subcategory="home gym equipment", intent="fitness", price_band="premium", price_min=100, price_max=500, review_coverage=4, amazon_depth=3, monetization=5),
    NicheCandidate("cycling helmets", "fitness", subcategory="cycling helmets", intent="fitness", price_band="mid", price_min=30, price_max=200, review_coverage=3, amazon_depth=4, monetization=3),
    NicheCandidate("hiking boots", "fitness", subcategory="hiking boots", intent="fitness", price_band="mid", price_min=80, price_max=250, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("camping tents", "outdoor", subcategory="camping tents", intent="travel", price_band="mid", price_min=60, price_max=400, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("sleeping bags", "outdoor", subcategory="sleeping bags", intent="travel", price_band="mid", price_min=30, price_max=200, review_coverage=3, amazon_depth=4, monetization=3),

    # Travel / EDC
    NicheCandidate("carry on luggage", "travel", subcategory="carry-on suitcase", intent="travel", price_band="premium", price_min=80, price_max=400, review_coverage=5, amazon_depth=5, monetization=5),
    NicheCandidate("travel backpacks", "travel", subcategory="travel backpacks", intent="travel", price_band="mid", price_min=40, price_max=200, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("packing cubes", "travel", subcategory="packing cubes", intent="travel", price_band="budget", price_min=15, price_max=50, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("noise cancelling earbuds for travel", "travel", subcategory="travel earbuds", intent="travel", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("portable chargers", "travel", subcategory="portable chargers", intent="travel", price_band="budget", price_min=20, price_max=80, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("power banks", "travel", subcategory="power banks", intent="travel", price_band="budget", price_min=20, price_max=80, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("travel adapters", "travel", subcategory="travel adapters", intent="travel", price_band="budget", price_min=10, price_max=40, review_coverage=3, amazon_depth=5, monetization=2),

    # Camera / video
    NicheCandidate("action cameras", "camera", subcategory="action cameras", intent="creative", price_band="premium", price_min=100, price_max=500, review_coverage=5, amazon_depth=4, monetization=5),
    NicheCandidate("vlogging cameras", "camera", subcategory="vlogging cameras", intent="creative", price_band="premium", price_min=200, price_max=800, review_coverage=4, amazon_depth=3, monetization=5),
    NicheCandidate("dash cams", "camera", subcategory="dash cams", intent="general", price_band="mid", price_min=40, price_max=250, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("ring lights", "camera", subcategory="ring lights", intent="creative", price_band="budget", price_min=15, price_max=80, review_coverage=3, amazon_depth=5, monetization=2),
    NicheCandidate("tripods", "camera", subcategory="tripods", intent="creative", price_band="mid", price_min=20, price_max=200, review_coverage=3, amazon_depth=5, monetization=3),
    NicheCandidate("camera backpacks", "camera", subcategory="camera backpacks", intent="creative", price_band="mid", price_min=30, price_max=150, review_coverage=3, amazon_depth=4, monetization=3),

    # Gaming
    NicheCandidate("gaming keyboards", "gaming", subcategory="gaming keyboards", intent="gaming", price_band="mid", price_min=50, price_max=200, review_coverage=5, amazon_depth=5, monetization=4),
    NicheCandidate("gaming chairs", "gaming", subcategory="gaming chairs", intent="gaming", price_band="mid", price_min=100, price_max=400, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("game capture cards", "gaming", subcategory="game capture cards", intent="gaming", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=3, monetization=4),
    NicheCandidate("gaming controllers", "gaming", subcategory="gaming controllers", intent="gaming", price_band="mid", price_min=30, price_max=200, review_coverage=4, amazon_depth=5, monetization=3),
    NicheCandidate("gaming mouse pads", "gaming", subcategory="gaming mouse pads", intent="gaming", price_band="budget", price_min=10, price_max=50, review_coverage=3, amazon_depth=5, monetization=2),

    # Streaming / content
    NicheCandidate("streaming microphones", "streaming", subcategory="streaming microphones", intent="creative", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),
    NicheCandidate("stream decks", "streaming", subcategory="stream decks", intent="creative", price_band="mid", price_min=50, price_max=250, review_coverage=3, amazon_depth=3, monetization=4),
    NicheCandidate("green screens", "streaming", subcategory="green screens", intent="creative", price_band="budget", price_min=20, price_max=100, review_coverage=3, amazon_depth=4, monetization=2),
    NicheCandidate("studio headphones", "streaming", subcategory="studio headphones", intent="creative", price_band="mid", price_min=50, price_max=300, review_coverage=4, amazon_depth=4, monetization=4),

    # Baby / kids (high conversion)
    NicheCandidate("baby monitors", "baby", subcategory="baby monitors", intent="general", price_band="mid", price_min=40, price_max=250, review_coverage=4, amazon_depth=5, monetization=4),
    NicheCandidate("car seats", "baby", subcategory="car seats", intent="general", price_band="mid", price_min=100, price_max=400, review_coverage=4, amazon_depth=4, monetization=5),
    NicheCandidate("strollers", "baby", subcategory="strollers", intent="general", price_band="premium", price_min=100, price_max=500, review_coverage=4, amazon_depth=4, monetization=5),
]

# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------


@dataclass
class NicheHistoryEntry:
    date: str
    niche: str
    video_id: str = ""
    category: str = ""
    subcategory: str = ""
    intent: str = ""
    seed_keywords: list[str] = field(default_factory=list)
    final_top5_asins: list[str] = field(default_factory=list)


def load_history() -> list[NicheHistoryEntry]:
    """Load niche history from disk."""
    if not HISTORY_PATH.is_file():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return [
            NicheHistoryEntry(
                date=e.get("date", ""),
                niche=e.get("niche", ""),
                video_id=e.get("video_id", ""),
                seed_keywords=e.get("seed_keywords", []),
                final_top5_asins=e.get("final_top5_asins", []),
            )
            for e in data
        ]
    except Exception:
        return []


def save_history(history: list[NicheHistoryEntry]) -> None:
    """Persist niche history to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "date": e.date,
            "niche": e.niche,
            "video_id": e.video_id,
            "seed_keywords": e.seed_keywords,
            "final_top5_asins": e.final_top5_asins,
        }
        for e in history
    ]
    HISTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_history(
    niche: str,
    date: str,
    *,
    video_id: str = "",
    asins: list[str] | None = None,
) -> None:
    """Add or update a niche history entry."""
    history = load_history()
    # Update existing entry for same date, or append
    for entry in history:
        if entry.date == date:
            entry.niche = niche
            entry.video_id = video_id
            if asins:
                entry.final_top5_asins = asins
            save_history(history)
            return
    history.append(NicheHistoryEntry(
        date=date,
        niche=niche,
        video_id=video_id,
        final_top5_asins=asins or [],
    ))
    save_history(history)


# ---------------------------------------------------------------------------
# Niche selection
# ---------------------------------------------------------------------------


def _recently_used(days: int = EXCLUSION_DAYS) -> set[str]:
    """Return niche keywords used in the last N days."""
    history = load_history()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days)
    ).strftime("%Y-%m-%d")

    return {
        e.niche.lower()
        for e in history
        if e.date >= cutoff
    }


def _date_seed(date_str: str) -> int:
    """Deterministic seed from date string, for stable ordering."""
    h = hashlib.sha256(date_str.encode()).hexdigest()
    return int(h[:8], 16)


def pick_niche(date_str: str | None = None) -> NicheCandidate:
    """Pick the best available niche for a given date.

    Deterministic: same date always picks the same niche (given same history).
    """
    if date_str is None:
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    used = _recently_used()

    # Filter to available niches
    available = [n for n in NICHE_POOL if n.keyword.lower() not in used]

    if not available:
        # Fallback: reset exclusion to 30 days
        used_30 = _recently_used(30)
        available = [n for n in NICHE_POOL if n.keyword.lower() not in used_30]

    if not available:
        raise RuntimeError("No available niches — all used recently")

    # Sort by score (descending), then use date seed for tiebreaking
    seed = _date_seed(date_str)
    available.sort(key=lambda n: (-n.score, hash((n.keyword, seed))))

    return available[0]


def list_available(days: int = EXCLUSION_DAYS) -> list[NicheCandidate]:
    """List all available niches (not used in last N days), sorted by score."""
    used = _recently_used(days)
    available = [n for n in NICHE_POOL if n.keyword.lower() not in used]
    available.sort(key=lambda n: -n.score)
    return available


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily niche picker")
    parser.add_argument("--date", default=None, help="Date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--list", action="store_true", help="List available niches")
    parser.add_argument("--history", action="store_true", help="Show recent history")
    parser.add_argument("--video-id", default="", help="Video ID to record")
    args = parser.parse_args()

    if args.history:
        history = load_history()
        if not history:
            print("No history yet.")
            return 0
        print(f"{'Date':<12} {'Niche':<35} {'Video ID'}")
        print("-" * 65)
        for e in history[-30:]:
            print(f"{e.date:<12} {e.niche:<35} {e.video_id}")
        return 0

    if args.list:
        available = list_available()
        print(f"Available niches ({len(available)}/{len(NICHE_POOL)}):\n")
        print(f"{'Score':>5}  {'Niche':<40} {'Category':<12} {'Price'}")
        print("-" * 75)
        for n in available[:30]:
            print(f"{n.score:5.1f}  {n.keyword:<40} {n.category:<12} ${n.price_min}-${n.price_max}")
        if len(available) > 30:
            print(f"  ... and {len(available) - 30} more")
        return 0

    # Pick niche
    date_str = args.date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    niche = pick_niche(date_str)

    print(f"Date:     {date_str}")
    print(f"Niche:    {niche.keyword}")
    print(f"Category: {niche.category}")
    print(f"Price:    ${niche.price_min}-${niche.price_max}")
    print(f"Score:    {niche.score:.1f}")

    # Record in history
    video_id = args.video_id or f"{niche.keyword.replace(' ', '-')}-{date_str}"
    update_history(niche.keyword, date_str, video_id=video_id)
    print(f"\nRecorded in {HISTORY_PATH}")
    print(f"Video ID: {video_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
