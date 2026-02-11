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
    price_min: int = 30
    price_max: int = 300
    review_coverage: int = 3   # 1-5 scale
    amazon_depth: int = 3      # 1-5 scale
    monetization: int = 3      # 1-5 scale

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
    NicheCandidate("wireless earbuds", "audio", 20, 350, 5, 5, 4),
    NicheCandidate("over-ear headphones", "audio", 50, 500, 5, 5, 5),
    NicheCandidate("noise cancelling headphones", "audio", 80, 450, 5, 5, 5),
    NicheCandidate("portable bluetooth speakers", "audio", 30, 300, 5, 5, 4),
    NicheCandidate("soundbars", "audio", 80, 500, 5, 4, 5),
    NicheCandidate("studio monitors", "audio", 100, 500, 4, 4, 4),
    NicheCandidate("podcast microphones", "audio", 50, 300, 4, 4, 4),
    NicheCandidate("USB microphones", "audio", 40, 250, 4, 4, 4),
    NicheCandidate("gaming headsets", "audio", 40, 300, 5, 5, 4),
    NicheCandidate("turntables", "audio", 80, 500, 4, 3, 4),
    NicheCandidate("bookshelf speakers", "audio", 80, 500, 4, 4, 4),

    # Computing / peripherals
    NicheCandidate("mechanical keyboards", "computing", 50, 300, 5, 5, 4),
    NicheCandidate("ergonomic keyboards", "computing", 50, 250, 4, 4, 4),
    NicheCandidate("wireless mice", "computing", 30, 150, 4, 5, 3),
    NicheCandidate("gaming mice", "computing", 30, 180, 5, 5, 3),
    NicheCandidate("webcams", "computing", 40, 200, 4, 4, 4),
    NicheCandidate("USB-C hubs", "computing", 25, 100, 4, 5, 3),
    NicheCandidate("external SSDs", "computing", 50, 250, 5, 5, 4),
    NicheCandidate("portable monitors", "computing", 100, 400, 4, 4, 4),
    NicheCandidate("laptop stands", "computing", 20, 80, 3, 5, 2),
    NicheCandidate("computer monitors 27 inch", "computing", 150, 600, 5, 5, 5),
    NicheCandidate("4K monitors", "computing", 200, 700, 5, 4, 5),
    NicheCandidate("gaming monitors", "computing", 150, 600, 5, 5, 5),

    # Home
    NicheCandidate("robot vacuums", "home", 150, 800, 5, 5, 5),
    NicheCandidate("air purifiers", "home", 50, 400, 5, 5, 4),
    NicheCandidate("humidifiers", "home", 30, 150, 4, 5, 3),
    NicheCandidate("dehumidifiers", "home", 100, 350, 4, 4, 4),
    NicheCandidate("space heaters", "home", 30, 150, 4, 5, 3),
    NicheCandidate("smart thermostats", "home", 80, 300, 4, 3, 4),
    NicheCandidate("smart locks", "home", 80, 300, 4, 4, 4),
    NicheCandidate("video doorbells", "home", 50, 250, 5, 4, 4),
    NicheCandidate("mesh wifi routers", "home", 100, 400, 5, 4, 5),
    NicheCandidate("wifi routers", "home", 50, 350, 5, 5, 4),
    NicheCandidate("smart plugs", "home", 10, 50, 3, 5, 2),
    NicheCandidate("smart light bulbs", "home", 10, 60, 3, 5, 2),
    NicheCandidate("electric toothbrushes", "home", 30, 200, 4, 5, 3),
    NicheCandidate("electric shavers", "home", 40, 300, 4, 4, 4),
    NicheCandidate("hair clippers", "home", 20, 100, 3, 4, 3),

    # Kitchen
    NicheCandidate("air fryers", "kitchen", 40, 200, 5, 5, 4),
    NicheCandidate("espresso machines", "kitchen", 100, 600, 5, 4, 5),
    NicheCandidate("coffee grinders", "kitchen", 30, 200, 4, 4, 3),
    NicheCandidate("drip coffee makers", "kitchen", 30, 200, 4, 5, 3),
    NicheCandidate("blenders", "kitchen", 30, 250, 4, 5, 4),
    NicheCandidate("stand mixers", "kitchen", 100, 500, 4, 3, 5),
    NicheCandidate("food processors", "kitchen", 50, 300, 4, 4, 4),
    NicheCandidate("instant pots", "kitchen", 50, 150, 4, 4, 3),
    NicheCandidate("toaster ovens", "kitchen", 40, 250, 4, 5, 4),
    NicheCandidate("electric kettles", "kitchen", 20, 100, 3, 5, 2),
    NicheCandidate("sous vide machines", "kitchen", 50, 250, 3, 4, 4),
    NicheCandidate("knife sets", "kitchen", 40, 300, 4, 5, 4),
    NicheCandidate("cast iron skillets", "kitchen", 20, 100, 3, 5, 2),
    NicheCandidate("nonstick cookware sets", "kitchen", 50, 250, 4, 5, 4),

    # Office / desk
    NicheCandidate("standing desks", "office", 200, 700, 5, 4, 5),
    NicheCandidate("office chairs", "office", 100, 500, 5, 5, 5),
    NicheCandidate("ergonomic office chairs", "office", 200, 800, 5, 4, 5),
    NicheCandidate("desk lamps", "office", 20, 100, 3, 5, 2),
    NicheCandidate("monitor arms", "office", 30, 150, 4, 5, 3),
    NicheCandidate("desk organizers", "office", 15, 60, 2, 5, 2),

    # Fitness / outdoor
    NicheCandidate("fitness trackers", "fitness", 30, 200, 5, 5, 4),
    NicheCandidate("smartwatches", "fitness", 100, 500, 5, 4, 5),
    NicheCandidate("running shoes", "fitness", 80, 200, 4, 5, 4),
    NicheCandidate("yoga mats", "fitness", 15, 80, 3, 5, 2),
    NicheCandidate("resistance bands", "fitness", 10, 50, 3, 5, 2),
    NicheCandidate("adjustable dumbbells", "fitness", 100, 500, 4, 3, 5),
    NicheCandidate("home gym equipment", "fitness", 100, 500, 4, 3, 5),
    NicheCandidate("cycling helmets", "fitness", 30, 200, 3, 4, 3),
    NicheCandidate("hiking boots", "fitness", 80, 250, 4, 4, 4),
    NicheCandidate("camping tents", "outdoor", 60, 400, 4, 4, 4),
    NicheCandidate("sleeping bags", "outdoor", 30, 200, 3, 4, 3),

    # Travel / EDC
    NicheCandidate("carry on luggage", "travel", 80, 400, 5, 5, 5),
    NicheCandidate("travel backpacks", "travel", 40, 200, 4, 5, 4),
    NicheCandidate("packing cubes", "travel", 15, 50, 3, 5, 2),
    NicheCandidate("noise cancelling earbuds for travel", "travel", 50, 300, 4, 4, 4),
    NicheCandidate("portable chargers", "travel", 20, 80, 4, 5, 3),
    NicheCandidate("power banks", "travel", 20, 80, 4, 5, 3),
    NicheCandidate("travel adapters", "travel", 10, 40, 3, 5, 2),

    # Camera / video
    NicheCandidate("action cameras", "camera", 100, 500, 5, 4, 5),
    NicheCandidate("vlogging cameras", "camera", 200, 800, 4, 3, 5),
    NicheCandidate("dash cams", "camera", 40, 250, 5, 5, 4),
    NicheCandidate("ring lights", "camera", 15, 80, 3, 5, 2),
    NicheCandidate("tripods", "camera", 20, 200, 3, 5, 3),
    NicheCandidate("camera backpacks", "camera", 30, 150, 3, 4, 3),

    # Gaming
    NicheCandidate("gaming keyboards", "gaming", 50, 200, 5, 5, 4),
    NicheCandidate("gaming chairs", "gaming", 100, 400, 4, 5, 4),
    NicheCandidate("game capture cards", "gaming", 50, 300, 4, 3, 4),
    NicheCandidate("gaming controllers", "gaming", 30, 200, 4, 5, 3),
    NicheCandidate("gaming mouse pads", "gaming", 10, 50, 3, 5, 2),

    # Streaming / content
    NicheCandidate("streaming microphones", "streaming", 50, 300, 4, 4, 4),
    NicheCandidate("stream decks", "streaming", 50, 250, 3, 3, 4),
    NicheCandidate("green screens", "streaming", 20, 100, 3, 4, 2),
    NicheCandidate("studio headphones", "streaming", 50, 300, 4, 4, 4),

    # Baby / kids (high conversion)
    NicheCandidate("baby monitors", "baby", 40, 250, 4, 5, 4),
    NicheCandidate("car seats", "baby", 100, 400, 4, 4, 5),
    NicheCandidate("strollers", "baby", 100, 500, 4, 4, 5),
]

# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------


@dataclass
class NicheHistoryEntry:
    date: str
    niche: str
    video_id: str = ""
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
