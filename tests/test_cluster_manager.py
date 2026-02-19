"""Tests for cluster_manager — weekly cluster rotation and micro-niche selection."""

from __future__ import annotations

import json
import tempfile
import unittest
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
# Helpers
# ---------------------------------------------------------------------------


def _sample_clusters():
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


class TestLoadClusters(unittest.TestCase):
    def test_load_clusters_all_valid(self):
        """All 8 real clusters load, each has exactly 5 micro-niches."""
        clusters = load_clusters()
        self.assertEqual(len(clusters), 8)
        for c in clusters:
            self.assertEqual(len(c.micro_niches), 5,
                             f"Cluster {c.slug} has {len(c.micro_niches)} micro-niches")

    def test_load_clusters_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            _write_clusters(clusters_path, _sample_clusters())
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                clusters = load_clusters()
                self.assertEqual(len(clusters), 3)
                self.assertEqual(clusters[0].slug, "alpha")
                self.assertEqual(len(clusters[0].micro_niches), 5)

    def test_load_clusters_empty(self):
        """Missing file returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                clusters = load_clusters()
                self.assertEqual(clusters, [])


# ---------------------------------------------------------------------------
# Tests: micro-niche fields
# ---------------------------------------------------------------------------


class TestMicroNicheFields(unittest.TestCase):
    def test_micro_niche_has_required_fields(self):
        """Every micro-niche in real clusters has buyer_pain, intent_phrase, etc."""
        clusters = load_clusters()
        for c in clusters:
            for mn in c.micro_niches:
                self.assertTrue(mn.subcategory, f"Missing subcategory in {c.slug}")
                self.assertTrue(mn.buyer_pain, f"Missing buyer_pain in {c.slug}/{mn.subcategory}")
                self.assertTrue(mn.intent_phrase, f"Missing intent_phrase in {c.slug}/{mn.subcategory}")
                self.assertGreater(mn.price_min, 0, f"Invalid price_min in {c.slug}/{mn.subcategory}")
                self.assertGreater(mn.price_max, mn.price_min,
                                   f"price_max <= price_min in {c.slug}/{mn.subcategory}")

    def test_price_floor_default(self):
        """Micro-niches default to price_min >= 25."""
        clusters = load_clusters()
        for c in clusters:
            for mn in c.micro_niches:
                self.assertGreaterEqual(mn.price_min, 25,
                                        f"{c.slug}/{mn.subcategory} has price_min={mn.price_min}")


# ---------------------------------------------------------------------------
# Tests: cluster history roundtrip
# ---------------------------------------------------------------------------


class TestClusterHistory(unittest.TestCase):
    def test_cluster_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_path = tmp_path / "cluster_history.json"
            with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
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
                self.assertEqual(len(loaded), 2)
                self.assertEqual(loaded[0].week_start, "2026-02-10")
                self.assertEqual(loaded[0].cluster_slug, "alpha")
                self.assertEqual(loaded[0].video_ids, ["vid-001", "vid-002"])
                self.assertEqual(loaded[1].cluster_slug, "beta")

    def test_cluster_history_empty(self):
        """Missing file returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_path = tmp_path / "cluster_history.json"
            with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                loaded = load_cluster_history()
                self.assertEqual(loaded, [])


# ---------------------------------------------------------------------------
# Tests: current_week_monday
# ---------------------------------------------------------------------------


class TestCurrentWeekMonday(unittest.TestCase):
    def test_thursday(self):
        self.assertEqual(current_week_monday("2026-02-12"), "2026-02-09")

    def test_monday(self):
        self.assertEqual(current_week_monday("2026-02-09"), "2026-02-09")

    def test_sunday(self):
        self.assertEqual(current_week_monday("2026-02-15"), "2026-02-09")

    def test_saturday(self):
        self.assertEqual(current_week_monday("2026-02-14"), "2026-02-09")

    def test_next_monday(self):
        self.assertEqual(current_week_monday("2026-02-16"), "2026-02-16")


# ---------------------------------------------------------------------------
# Tests: pick_cluster
# ---------------------------------------------------------------------------


class TestPickCluster(unittest.TestCase):
    def test_cluster_no_repeat_6_weeks(self):
        """pick_cluster skips clusters used in the last 6 weeks."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            _write_history(history_path, [
                {"week_start": "2026-01-26", "cluster_slug": "alpha", "video_ids": ["v1"]},
                {"week_start": "2026-02-02", "cluster_slug": "beta", "video_ids": ["v2"]},
            ])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                cluster = pick_cluster("2026-02-12")
                self.assertEqual(cluster.slug, "gamma")

    def test_cluster_picks_already_assigned_for_week(self):
        """If cluster already assigned for this week, return it."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            monday = current_week_monday("2026-02-12")
            _write_history(history_path, [
                {"week_start": monday, "cluster_slug": "beta", "video_ids": ["v1"]},
            ])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                cluster = pick_cluster("2026-02-12")
                self.assertEqual(cluster.slug, "beta")

    def test_cluster_picks_first_available(self):
        """With no history, picks first cluster by slug order."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            _write_history(history_path, [])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                cluster = pick_cluster("2026-02-12")
                self.assertEqual(cluster.slug, "alpha")


# ---------------------------------------------------------------------------
# Tests: pick_micro_niche
# ---------------------------------------------------------------------------


class TestPickMicroNiche(unittest.TestCase):
    def test_pick_micro_niche_sequential(self):
        """Picks unused micro-niche from cluster in order."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            _write_history(history_path, [])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                clusters = load_clusters()
                alpha = clusters[0]
                mn = pick_micro_niche(alpha, [])
                self.assertEqual(mn.subcategory, "alpha niche 0")

    def test_pick_micro_niche_advances(self):
        """After 2 videos, picks the 3rd micro-niche."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            monday = current_week_monday("2026-02-12")
            _write_history(history_path, [
                {"week_start": monday, "cluster_slug": "alpha", "video_ids": ["v1", "v2"]},
            ])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                clusters = load_clusters()
                alpha = clusters[0]
                mn = pick_micro_niche(alpha, ["v1", "v2"])
                self.assertEqual(mn.subcategory, "alpha niche 2")

    def test_pick_micro_niche_wraps(self):
        """After all 5 used, wraps back to index 0."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clusters_path = tmp_path / "clusters.json"
            history_path = tmp_path / "cluster_history.json"
            _write_clusters(clusters_path, _sample_clusters())
            monday = current_week_monday("2026-02-12")
            _write_history(history_path, [
                {"week_start": monday, "cluster_slug": "alpha",
                 "video_ids": ["v1", "v2", "v3", "v4", "v5"]},
            ])
            with patch("tools.cluster_manager.CLUSTERS_PATH", clusters_path), \
                 patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                clusters = load_clusters()
                alpha = clusters[0]
                mn = pick_micro_niche(alpha, ["v1", "v2", "v3", "v4", "v5"])
                self.assertEqual(mn.subcategory, "alpha niche 0")


# ---------------------------------------------------------------------------
# Tests: update_cluster_history
# ---------------------------------------------------------------------------


class TestUpdateClusterHistory(unittest.TestCase):
    def test_update_cluster_history_new(self):
        """Creates new entry when none exists for the week."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_path = tmp_path / "cluster_history.json"
            with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                update_cluster_history("alpha", "2026-02-10", "vid-001")
                loaded = load_cluster_history()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].video_ids, ["vid-001"])

    def test_update_cluster_history_append(self):
        """Appends video_id to existing entry."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_path = tmp_path / "cluster_history.json"
            _write_history(history_path, [
                {"week_start": "2026-02-10", "cluster_slug": "alpha", "video_ids": ["vid-001"]},
            ])
            with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                update_cluster_history("alpha", "2026-02-10", "vid-002")
                loaded = load_cluster_history()
                self.assertEqual(loaded[0].video_ids, ["vid-001", "vid-002"])

    def test_update_cluster_history_no_duplicate(self):
        """Does not duplicate video_id."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_path = tmp_path / "cluster_history.json"
            _write_history(history_path, [
                {"week_start": "2026-02-10", "cluster_slug": "alpha", "video_ids": ["vid-001"]},
            ])
            with patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", history_path), \
                 patch("tools.cluster_manager.DATA_DIR", tmp_path):
                update_cluster_history("alpha", "2026-02-10", "vid-001")
                loaded = load_cluster_history()
                self.assertEqual(loaded[0].video_ids, ["vid-001"])
