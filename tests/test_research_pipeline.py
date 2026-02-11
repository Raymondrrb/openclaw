"""Tests for the reviews-first research pipeline.

Covers: niche_picker, top5_ranker, reviews_research (extraction logic).
No browser/API calls — all external I/O is mocked.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


class TestNichePicker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.history_path = self.data_dir / "niche_history.json"
        self.history_path.write_text("[]", encoding="utf-8")
        self.patchers = [
            patch("tools.niche_picker.DATA_DIR", self.data_dir),
            patch("tools.niche_picker.HISTORY_PATH", self.history_path),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_pick_returns_niche(self):
        from tools.niche_picker import pick_niche
        niche = pick_niche("2026-02-11")
        self.assertTrue(niche.keyword)
        self.assertGreater(niche.score, 0)

    def test_pick_deterministic(self):
        from tools.niche_picker import pick_niche
        n1 = pick_niche("2026-02-11")
        n2 = pick_niche("2026-02-11")
        self.assertEqual(n1.keyword, n2.keyword)

    def test_pick_different_days_different_after_use(self):
        from tools.niche_picker import pick_niche, update_history
        n1 = pick_niche("2026-02-11")
        update_history(n1.keyword, "2026-02-11")
        n2 = pick_niche("2026-02-12")
        # After recording n1, n2 should be different
        self.assertNotEqual(n1.keyword, n2.keyword)

    def test_exclusion_60_days(self):
        from tools.niche_picker import pick_niche, update_history, list_available, NICHE_POOL
        # Record a niche
        n = pick_niche("2026-02-11")
        update_history(n.keyword, "2026-02-11")
        available = list_available()
        used_keywords = {a.keyword for a in available}
        self.assertNotIn(n.keyword, used_keywords)

    def test_history_persistence(self):
        from tools.niche_picker import update_history, load_history
        update_history("test niche", "2026-01-01", video_id="test-vid")
        history = load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].niche, "test niche")
        self.assertEqual(history[0].video_id, "test-vid")

    def test_list_available_count(self):
        from tools.niche_picker import list_available, NICHE_POOL
        available = list_available()
        self.assertEqual(len(available), len(NICHE_POOL))


class TestTop5Ranker(unittest.TestCase):
    def _make_product(self, name, evidence_count=1, confidence="high", price="$99.99", claims=None):
        return {
            "product_name": name,
            "brand": name.split()[0],
            "asin": f"B00TEST{name[:3].upper()}",
            "amazon_url": f"https://amazon.com/dp/B00TEST{name[:3].upper()}",
            "affiliate_url": f"https://amazon.com/dp/B00TEST{name[:3].upper()}?tag=test-20",
            "amazon_title": name,
            "amazon_price": price,
            "amazon_rating": "4.5",
            "amazon_reviews": "5000",
            "match_confidence": confidence,
            "verification_method": "browser",
            "evidence": [
                {"source": f"Source{i}", "url": f"https://example.com/{i}", "label": ""}
                for i in range(evidence_count)
            ],
            "key_claims": claims or [],
        }

    def test_select_top5_returns_5(self):
        from tools.top5_ranker import select_top5
        products = [self._make_product(f"Product {i}", evidence_count=i) for i in range(1, 10)]
        top5 = select_top5(products)
        self.assertEqual(len(top5), 5)

    def test_select_top5_has_ranks(self):
        from tools.top5_ranker import select_top5
        products = [self._make_product(f"Product {i}", evidence_count=i) for i in range(1, 10)]
        top5 = select_top5(products)
        ranks = sorted(p["rank"] for p in top5)
        self.assertEqual(ranks, [1, 2, 3, 4, 5])

    def test_select_top5_evidence_matters(self):
        from tools.top5_ranker import select_top5
        # Product with more evidence should rank higher
        products = [
            self._make_product("Weak Product", evidence_count=1),
            self._make_product("Strong Product", evidence_count=5),
        ]
        top5 = select_top5(products)
        self.assertEqual(top5[0]["product_name"], "Strong Product")

    def test_select_top5_few_products(self):
        from tools.top5_ranker import select_top5
        products = [self._make_product(f"Product {i}") for i in range(1, 4)]
        top5 = select_top5(products)
        self.assertEqual(len(top5), 3)

    def test_category_diversity(self):
        from tools.top5_ranker import select_top5
        products = [
            self._make_product("Premium Pro", evidence_count=3, price="$299", claims=["best premium"]),
            self._make_product("Budget Basic", evidence_count=3, price="$29", claims=["best budget"]),
            self._make_product("Overall Winner", evidence_count=4, claims=["best overall"]),
            self._make_product("Value King", evidence_count=3, price="$79", claims=["best value"]),
            self._make_product("Travel Pick", evidence_count=2, claims=["best for travel"]),
            self._make_product("Gaming Pick", evidence_count=2, claims=["best for gaming"]),
            self._make_product("Music Pick", evidence_count=2, claims=["best for music"]),
        ]
        top5 = select_top5(products)
        categories = {p.get("category_label") for p in top5}
        # Should have at least 3 different categories
        self.assertGreaterEqual(len(categories), 3)

    def test_write_products_json(self):
        from tools.top5_ranker import select_top5, write_products_json
        products = [self._make_product(f"Product {i}", evidence_count=i) for i in range(1, 7)]
        top5 = select_top5(products)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "products.json"
            write_products_json(top5, "test niche", out, video_id="test-vid")
            self.assertTrue(out.is_file())
            data = json.loads(out.read_text())
            self.assertEqual(len(data["products"]), 5)
            self.assertEqual(data["niche"], "test niche")
            self.assertEqual(data["video_id"], "test-vid")


class TestReviewsExtraction(unittest.TestCase):
    def test_extract_products_from_snippet(self):
        from tools.reviews_research import _extract_products_from_snippet
        snippet = "The Sony WF-1000XM5 is our top pick, followed by the Apple AirPods Pro 2."
        products = _extract_products_from_snippet(snippet)
        names_lower = [p.lower() for p in products]
        # Should find Sony and Apple products
        self.assertTrue(any("sony" in n for n in names_lower))
        self.assertTrue(any("apple" in n for n in names_lower))

    def test_extract_brand(self):
        from tools.reviews_research import _extract_brand
        self.assertEqual(_extract_brand("Sony WF-1000XM5"), "Sony")
        self.assertEqual(_extract_brand("Apple AirPods Pro"), "Apple")
        self.assertEqual(_extract_brand("Bose QuietComfort Ultra"), "Bose")

    def test_normalize_product_name(self):
        from tools.reviews_research import _normalize_product_name
        self.assertEqual(
            _normalize_product_name("Sony WF-1000XM5"),
            "sony wf-1000xm5",
        )

    def test_extract_label(self):
        from tools.reviews_research import _extract_label
        self.assertEqual(
            _extract_label("Best Overall Earbuds", "The Sony WF-1000XM5 is amazing"),
            "best overall",
        )
        self.assertEqual(
            _extract_label("Best Budget Earbuds", "Cheap and cheerful"),
            "best budget",
        )


class TestAmazonVerify(unittest.TestCase):
    def test_title_similarity(self):
        from tools.amazon_verify import _title_similarity
        # High similarity
        score = _title_similarity(
            "Sony WF-1000XM5",
            "Sony WF-1000XM5 Truly Wireless Bluetooth Noise Canceling Earbuds"
        )
        self.assertGreater(score, 0.5)

        # Low similarity
        score = _title_similarity(
            "Sony WF-1000XM5",
            "Generic Bluetooth Earbuds Cheap Wireless"
        )
        self.assertLess(score, 0.3)

    def test_make_affiliate_url(self):
        from tools.amazon_verify import _make_affiliate_url
        url = _make_affiliate_url("B0C8P2QH1Z", "rayviewslab-20")
        self.assertEqual(url, "https://www.amazon.com/dp/B0C8P2QH1Z?tag=rayviewslab-20")

    def test_paapi_not_available(self):
        from tools.amazon_verify import _paapi_available
        # Should be False when env vars are not set
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_paapi_available())


if __name__ == "__main__":
    unittest.main()
