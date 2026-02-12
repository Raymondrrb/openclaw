"""Weekly cluster-based content strategy for Rayviews.

Replaces random daily niche picking with thematic weekly clusters.
Each cluster has 5 micro-niches with buyer pain, intent, and price range.
Clusters rotate on a 6-week no-repeat schedule.

Stdlib only — no external deps.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import project_root

DATA_DIR = project_root() / "data"
CLUSTERS_PATH = DATA_DIR / "clusters.json"
CLUSTER_HISTORY_PATH = DATA_DIR / "cluster_history.json"

NO_REPEAT_WEEKS = 6


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MicroNicheDef:
    subcategory: str           # "ergonomic office chairs"
    buyer_pain: str            # "lower back pain from 8+ hours sitting"
    intent_phrase: str         # "best office chairs for lower back pain"
    price_min: int = 120
    price_max: int = 300
    must_have_features: list[str] = field(default_factory=list)
    forbidden_variants: list[str] = field(default_factory=list)


@dataclass
class ClusterDef:
    name: str                  # "Office Comfort & Back Pain"
    slug: str                  # "office_comfort"
    micro_niches: list[MicroNicheDef] = field(default_factory=list)


@dataclass
class ClusterHistoryEntry:
    week_start: str            # "2026-02-10" (Monday)
    cluster_slug: str
    video_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_clusters() -> list[ClusterDef]:
    """Load cluster definitions from data/clusters.json."""
    if not CLUSTERS_PATH.is_file():
        return []
    data = json.loads(CLUSTERS_PATH.read_text(encoding="utf-8"))
    clusters = []
    for c in data:
        micro_niches = [
            MicroNicheDef(
                subcategory=mn["subcategory"],
                buyer_pain=mn["buyer_pain"],
                intent_phrase=mn["intent_phrase"],
                price_min=mn.get("price_min", 120),
                price_max=mn.get("price_max", 300),
                must_have_features=mn.get("must_have_features", []),
                forbidden_variants=mn.get("forbidden_variants", []),
            )
            for mn in c.get("micro_niches", [])
        ]
        clusters.append(ClusterDef(
            name=c["name"],
            slug=c["slug"],
            micro_niches=micro_niches,
        ))
    return clusters


def load_cluster_history() -> list[ClusterHistoryEntry]:
    """Load cluster rotation history from data/cluster_history.json."""
    if not CLUSTER_HISTORY_PATH.is_file():
        return []
    try:
        data = json.loads(CLUSTER_HISTORY_PATH.read_text(encoding="utf-8"))
        return [
            ClusterHistoryEntry(
                week_start=e["week_start"],
                cluster_slug=e["cluster_slug"],
                video_ids=e.get("video_ids", []),
            )
            for e in data
        ]
    except Exception:
        return []


def save_cluster_history(entries: list[ClusterHistoryEntry]) -> None:
    """Persist cluster history to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "week_start": e.week_start,
            "cluster_slug": e.cluster_slug,
            "video_ids": e.video_ids,
        }
        for e in entries
    ]
    CLUSTER_HISTORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Week calculation
# ---------------------------------------------------------------------------


def current_week_monday(date_str: str) -> str:
    """Return the Monday of the week containing date_str (YYYY-MM-DD)."""
    d = datetime.date.fromisoformat(date_str)
    monday = d - datetime.timedelta(days=d.weekday())
    return monday.isoformat()


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------


def pick_cluster(date_str: str) -> ClusterDef:
    """Pick a cluster not used in the last NO_REPEAT_WEEKS weeks.

    Deterministic: picks the first available cluster by slug order.
    Raises ValueError if all clusters are exhausted (shouldn't happen
    with 8 clusters and 6-week exclusion).
    """
    clusters = load_clusters()
    if not clusters:
        raise ValueError("No clusters defined in data/clusters.json")

    history = load_cluster_history()
    monday = current_week_monday(date_str)

    # Check if a cluster is already assigned for this week
    for entry in history:
        if entry.week_start == monday:
            for c in clusters:
                if c.slug == entry.cluster_slug:
                    return c

    # Find clusters used in the last NO_REPEAT_WEEKS weeks
    cutoff = (
        datetime.date.fromisoformat(monday)
        - datetime.timedelta(weeks=NO_REPEAT_WEEKS)
    ).isoformat()

    recently_used = {
        e.cluster_slug
        for e in history
        if e.week_start >= cutoff and e.week_start != monday
    }

    # Pick first available cluster (deterministic by slug order)
    available = sorted(
        [c for c in clusters if c.slug not in recently_used],
        key=lambda c: c.slug,
    )

    if not available:
        raise ValueError(
            f"All {len(clusters)} clusters used in last {NO_REPEAT_WEEKS} weeks. "
            f"Add more clusters to data/clusters.json."
        )

    return available[0]


def pick_micro_niche(
    cluster: ClusterDef, used_video_ids: list[str],
) -> MicroNicheDef:
    """Pick the next unused micro-niche from the cluster.

    Micro-niches are picked in order. If all 5 have been used
    (based on video_ids count in the current week's history entry),
    wraps back to the first one.
    """
    history = load_cluster_history()

    # Count how many micro-niches from this cluster have been used this week
    used_count = 0
    for entry in history:
        if entry.cluster_slug == cluster.slug:
            used_count = len(entry.video_ids)
            break

    # Pick next in sequence (wrapping if needed)
    idx = used_count % len(cluster.micro_niches)
    return cluster.micro_niches[idx]


def update_cluster_history(
    cluster_slug: str, week_start: str, video_id: str,
) -> None:
    """Append video_id to the cluster history for this week."""
    history = load_cluster_history()

    for entry in history:
        if entry.week_start == week_start and entry.cluster_slug == cluster_slug:
            if video_id not in entry.video_ids:
                entry.video_ids.append(video_id)
            save_cluster_history(history)
            return

    # New entry
    history.append(ClusterHistoryEntry(
        week_start=week_start,
        cluster_slug=cluster_slug,
        video_ids=[video_id],
    ))
    save_cluster_history(history)
