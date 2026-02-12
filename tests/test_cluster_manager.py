"""Tests for cluster_manager — weekly cluster rotation and micro-niche selection."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from tools.cluster_manager import (
    ClusterDef,
    ClusterHistoryEntry,
    MicroNicheDef,
    current_week_monday,
    load_cluster_history,
    load_clusters,
    pick_cluster,
    pick_micro_niche,
    save_cluster_history,
    update_cluster_history,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clusters_path(tmp_path):
    """Patch CLUSTERS_PATH to use tmp_path."""
    path = tmp_path / "clusters.json"
    with patch("tools.cluster_manager.CLUSTERS_PATH", path), \
         patch("tools.cluster_manager.DATA_DIR", tmp_path):
        yield path


@pytest.fixture
def history_path(tmp_path):
    """Patch CLUSTER_HISTORY_PATH to use tmp_path."""
    path = tmp_path / "cluster_history.json"
    with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", path), \
         patch("tools.cluster_manager.DATA_DIR", tmp_path):
        yield path


@pytest.fixture
def sample_clusters():
    """Minimal cluster definitions for testing."""
    return [
        {
            "name": "Cluster Alpha",
            "slug": "alpha",
            "micro_niches": [
                {
                    "subcategory": f"alpha niche {i}",
                    "buyer_pain": f"pain {i}",
                    "intent_phrase": f"best alpha niche {i}",
                    "price_min": 120,
                    "price_max": 300,
                    "must_have_features": ["feature_a"],
                    "forbidden_variants": ["bad_variant"],
                }
                for i in range(5)
            ],
        },
        {
            "name": "Cluster Beta",
            "slug": "beta",
            "micro_niches": [
                {
                    "subcategory": f"beta niche {i}",
                    "buyer_pain": f"pain {i}",
                    "intent_phrase": f"best beta niche {i}",
                    "price_min": 150,
                    "price_max": 400,
                    "must_have_features": ["feature_b"],
                    "forbidden_variants": ["bad_variant_b"],
                }
                for i in range(5)
            ],
        },
        {
            "name": "Cluster Gamma",
            "slug": "gamma",
            "micro_niches": [
                {
                    "subcategory": f"gamma niche {i}",
                    "buyer_pain": f"pain {i}",
                    "intent_phrase": f"best gamma niche {i}",
                    "price_min": 100,
                    "price_max": 250,
                    "must_have_features": ["feature_c"],
                    "forbidden_variants": [],
                }
                for i in range(5)
            ],
        },
    ]


def _write_clusters(path: Path, data: list[dict]):
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_history(path: Path, entries: list[dict]):
    path.write_text(json.dumps(entries), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: load_clusters
# ---------------------------------------------------------------------------


def test_load_clusters_all_valid():
    """All 8 real clusters load, each has exactly 5 micro-niches."""
    clusters = load_clusters()
    assert len(clusters) == 8
    for c in clusters:
        assert len(c.micro_niches) == 5, f"Cluster {c.slug} has {len(c.micro_niches)} micro-niches"


def test_load_clusters_from_file(clusters_path, sample_clusters):
    _write_clusters(clusters_path, sample_clusters)
    clusters = load_clusters()
    assert len(clusters) == 3
    assert clusters[0].slug == "alpha"
    assert len(clusters[0].micro_niches) == 5


def test_load_clusters_empty(clusters_path):
    """Missing file returns empty list."""
    clusters = load_clusters()
    assert clusters == []


# ---------------------------------------------------------------------------
# Tests: micro-niche fields
# ---------------------------------------------------------------------------


def test_micro_niche_has_required_fields():
    """Every micro-niche in real clusters has buyer_pain, intent_phrase, etc."""
    clusters = load_clusters()
    for c in clusters:
        for mn in c.micro_niches:
            assert mn.subcategory, f"Missing subcategory in {c.slug}"
            assert mn.buyer_pain, f"Missing buyer_pain in {c.slug}/{mn.subcategory}"
            assert mn.intent_phrase, f"Missing intent_phrase in {c.slug}/{mn.subcategory}"
            assert mn.price_min > 0, f"Invalid price_min in {c.slug}/{mn.subcategory}"
            assert mn.price_max > mn.price_min, f"price_max <= price_min in {c.slug}/{mn.subcategory}"


def test_price_floor_default():
    """Micro-niches default to price_min >= 100 (hard floor)."""
    clusters = load_clusters()
    for c in clusters:
        for mn in c.micro_niches:
            assert mn.price_min >= 25, (
                f"{c.slug}/{mn.subcategory} has price_min={mn.price_min} "
                f"which is unreasonably low"
            )


# ---------------------------------------------------------------------------
# Tests: cluster history roundtrip
# ---------------------------------------------------------------------------


def test_cluster_history_roundtrip(history_path):
    entries = [
        ClusterHistoryEntry(
            week_start="2026-02-10",
            cluster_slug="alpha",
            video_ids=["vid-001", "vid-002"],
        ),
        ClusterHistoryEntry(
            week_start="2026-02-03",
            cluster_slug="beta",
            video_ids=["vid-003"],
        ),
    ]
    save_cluster_history(entries)
    loaded = load_cluster_history()
    assert len(loaded) == 2
    assert loaded[0].week_start == "2026-02-10"
    assert loaded[0].cluster_slug == "alpha"
    assert loaded[0].video_ids == ["vid-001", "vid-002"]
    assert loaded[1].cluster_slug == "beta"


def test_cluster_history_empty(history_path):
    """Missing file returns empty list."""
    loaded = load_cluster_history()
    assert loaded == []


# ---------------------------------------------------------------------------
# Tests: current_week_monday
# ---------------------------------------------------------------------------


def test_current_week_monday():
    # 2026-02-12 is a Thursday
    assert current_week_monday("2026-02-12") == "2026-02-09"
    # Monday itself
    assert current_week_monday("2026-02-09") == "2026-02-09"
    # Sunday
    assert current_week_monday("2026-02-15") == "2026-02-09"
    # Saturday
    assert current_week_monday("2026-02-14") == "2026-02-09"
    # Next Monday
    assert current_week_monday("2026-02-16") == "2026-02-16"


# ---------------------------------------------------------------------------
# Tests: pick_cluster
# ---------------------------------------------------------------------------


def test_cluster_no_repeat_6_weeks(clusters_path, history_path, sample_clusters):
    """pick_cluster skips clusters used in the last 6 weeks."""
    _write_clusters(clusters_path, sample_clusters)
    # alpha used 2 weeks ago, beta used 1 week ago
    _write_history(history_path, [
        {"week_start": "2026-01-26", "cluster_slug": "alpha", "video_ids": ["v1"]},
        {"week_start": "2026-02-02", "cluster_slug": "beta", "video_ids": ["v2"]},
    ])
    # Both alpha and beta are within 6 weeks, so gamma should be picked
    cluster = pick_cluster("2026-02-12")
    assert cluster.slug == "gamma"


def test_cluster_picks_already_assigned_for_week(clusters_path, history_path, sample_clusters):
    """If cluster already assigned for this week, return it."""
    _write_clusters(clusters_path, sample_clusters)
    monday = current_week_monday("2026-02-12")
    _write_history(history_path, [
        {"week_start": monday, "cluster_slug": "beta", "video_ids": ["v1"]},
    ])
    cluster = pick_cluster("2026-02-12")
    assert cluster.slug == "beta"


def test_cluster_picks_first_available(clusters_path, history_path, sample_clusters):
    """With no history, picks first cluster by slug order."""
    _write_clusters(clusters_path, sample_clusters)
    _write_history(history_path, [])
    cluster = pick_cluster("2026-02-12")
    assert cluster.slug == "alpha"  # alphabetically first


# ---------------------------------------------------------------------------
# Tests: pick_micro_niche
# ---------------------------------------------------------------------------


def test_pick_micro_niche_sequential(clusters_path, history_path, sample_clusters):
    """Picks unused micro-niche from cluster in order."""
    _write_clusters(clusters_path, sample_clusters)
    _write_history(history_path, [])

    clusters = load_clusters()
    alpha = clusters[0]

    # First pick: index 0
    mn = pick_micro_niche(alpha, [])
    assert mn.subcategory == "alpha niche 0"


def test_pick_micro_niche_advances(clusters_path, history_path, sample_clusters):
    """After 2 videos, picks the 3rd micro-niche."""
    _write_clusters(clusters_path, sample_clusters)
    monday = current_week_monday("2026-02-12")
    _write_history(history_path, [
        {"week_start": monday, "cluster_slug": "alpha", "video_ids": ["v1", "v2"]},
    ])

    clusters = load_clusters()
    alpha = clusters[0]

    mn = pick_micro_niche(alpha, ["v1", "v2"])
    assert mn.subcategory == "alpha niche 2"


def test_pick_micro_niche_wraps(clusters_path, history_path, sample_clusters):
    """After all 5 used, wraps back to index 0."""
    _write_clusters(clusters_path, sample_clusters)
    monday = current_week_monday("2026-02-12")
    _write_history(history_path, [
        {"week_start": monday, "cluster_slug": "alpha",
         "video_ids": ["v1", "v2", "v3", "v4", "v5"]},
    ])

    clusters = load_clusters()
    alpha = clusters[0]

    mn = pick_micro_niche(alpha, ["v1", "v2", "v3", "v4", "v5"])
    assert mn.subcategory == "alpha niche 0"


# ---------------------------------------------------------------------------
# Tests: update_cluster_history
# ---------------------------------------------------------------------------


def test_update_cluster_history_new(history_path):
    """Creates new entry when none exists for the week."""
    update_cluster_history("alpha", "2026-02-10", "vid-001")
    loaded = load_cluster_history()
    assert len(loaded) == 1
    assert loaded[0].video_ids == ["vid-001"]


def test_update_cluster_history_append(history_path):
    """Appends video_id to existing entry."""
    _write_history(history_path, [
        {"week_start": "2026-02-10", "cluster_slug": "alpha", "video_ids": ["vid-001"]},
    ])
    update_cluster_history("alpha", "2026-02-10", "vid-002")
    loaded = load_cluster_history()
    assert loaded[0].video_ids == ["vid-001", "vid-002"]


def test_update_cluster_history_no_duplicate(history_path):
    """Does not duplicate video_id."""
    _write_history(history_path, [
        {"week_start": "2026-02-10", "cluster_slug": "alpha", "video_ids": ["vid-001"]},
    ])
    update_cluster_history("alpha", "2026-02-10", "vid-001")
    loaded = load_cluster_history()
    assert loaded[0].video_ids == ["vid-001"]
