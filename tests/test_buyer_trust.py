"""Tests for buyer_trust module — regret scoring, confidence tagging, publish readiness."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lib.buyer_trust import (
    CONFIDENCE_EDITORIAL,
    CONFIDENCE_MEASURED,
    CONFIDENCE_USER,
    CheckItem,
    EvidenceRow,
    PublishReadiness,
    RegretScore,
    ScoreCard,
    confidence_tag,
    publish_readiness_check,
    regret_score,
    target_audience_text,
)


# ---------------------------------------------------------------------------
# confidence_tag
# ---------------------------------------------------------------------------


class TestConfidenceTag(unittest.TestCase):
    def test_measured_with_unit(self):
        self.assertEqual(confidence_tag("Battery lasts 30 hours on a single charge"), CONFIDENCE_MEASURED)

    def test_measured_with_db(self):
        self.assertEqual(confidence_tag("40dB noise reduction measured in lab test"), CONFIDENCE_MEASURED)

    def test_measured_with_test_keyword(self):
        self.assertEqual(confidence_tag("RTINGS tested the frequency response"), CONFIDENCE_MEASURED)

    def test_editorial_opinion(self):
        self.assertEqual(confidence_tag("Great sound quality and comfortable fit"), CONFIDENCE_EDITORIAL)

    def test_user_reported(self):
        self.assertEqual(confidence_tag("Many users report Bluetooth connectivity issues"), CONFIDENCE_USER)

    def test_user_amazon_review(self):
        self.assertEqual(confidence_tag("Amazon reviews mention the build quality"), CONFIDENCE_USER)

    def test_editorial_default(self):
        self.assertEqual(confidence_tag("Excellent noise cancellation"), CONFIDENCE_EDITORIAL)


# ---------------------------------------------------------------------------
# EvidenceRow
# ---------------------------------------------------------------------------


class TestEvidenceRow(unittest.TestCase):
    def test_auto_confidence(self):
        row = EvidenceRow(claim="Battery rated 40 hours", source="RTINGS")
        self.assertEqual(row.confidence, CONFIDENCE_MEASURED)

    def test_explicit_confidence(self):
        row = EvidenceRow(claim="sounds great", source="PCMag", confidence="editorial")
        self.assertEqual(row.confidence, "editorial")


# ---------------------------------------------------------------------------
# regret_score
# ---------------------------------------------------------------------------


def _make_product(**overrides):
    """Build a product dict with sensible defaults."""
    base = {
        "product_name": "Test Product X",
        "brand": "TestBrand",
        "amazon_price": "$149.99",
        "amazon_reviews": "5000",
        "match_confidence": "high",
        "evidence": [
            {
                "source": "Wirecutter",
                "reasons": ["Battery lasts 30 hours on a single charge", "Comfortable fit"],
            },
            {
                "source": "RTINGS",
                "reasons": ["Measured 38dB ANC reduction", "Flat frequency response"],
            },
        ],
        "key_claims": ["Best overall pick", "However, the case is bulky"],
        "category_label": "No-Regret Pick",
    }
    base.update(overrides)
    return base


class TestRegretScore(unittest.TestCase):
    def test_good_product_low_regret(self):
        """Well-evidenced product with downside gets low regret."""
        p = _make_product()
        rs = regret_score(p)
        self.assertEqual(rs.source_count_penalty, 0.0)
        self.assertEqual(rs.downside_penalty, 0.0)  # "However, the case is bulky" found
        self.assertEqual(rs.evidence_quality_penalty, 0.0)  # has measured claims
        self.assertLess(rs.total, 3.0)

    def test_single_source_penalty(self):
        p = _make_product(evidence=[{
            "source": "Wirecutter",
            "reasons": ["Good sound quality"],
        }])
        rs = regret_score(p)
        self.assertEqual(rs.source_count_penalty, 2.0)

    def test_no_downside_penalty(self):
        p = _make_product(key_claims=["Great product", "Best overall"])
        # No downside keywords in claims or evidence
        p["evidence"] = [{
            "source": "Wirecutter",
            "reasons": ["Great sound", "Nice design"],
        }, {
            "source": "RTINGS",
            "reasons": ["Good bass", "Flat response"],
        }]
        rs = regret_score(p)
        self.assertEqual(rs.downside_penalty, 3.0)

    def test_cheap_price_penalty(self):
        p = _make_product(amazon_price="$15.99")
        rs = regret_score(p)
        self.assertEqual(rs.price_extreme_penalty, 2.0)

    def test_expensive_price_penalty(self):
        p = _make_product(amazon_price="$599.99")
        rs = regret_score(p)
        self.assertEqual(rs.price_extreme_penalty, 2.0)

    def test_mid_range_no_price_penalty(self):
        p = _make_product(amazon_price="$149.99")
        rs = regret_score(p)
        self.assertEqual(rs.price_extreme_penalty, 0.0)

    def test_no_measured_evidence_penalty(self):
        p = _make_product(evidence=[{
            "source": "Wirecutter",
            "reasons": ["Great sound", "Comfortable"],
        }, {
            "source": "RTINGS",
            "reasons": ["Nice design", "Good value"],
        }], key_claims=["Good product", "However, slightly bulky"])
        rs = regret_score(p)
        self.assertEqual(rs.evidence_quality_penalty, 1.0)

    def test_warranty_no_penalty_when_present(self):
        p = _make_product(key_claims=[
            "Best overall", "2-year warranty included",
            "However, the case is bulky",
        ])
        rs = regret_score(p)
        self.assertEqual(rs.warranty_penalty, 0.0)

    def test_warranty_penalty_when_missing(self):
        p = _make_product()
        rs = regret_score(p)
        self.assertEqual(rs.warranty_penalty, 1.0)


# ---------------------------------------------------------------------------
# ScoreCard
# ---------------------------------------------------------------------------


class TestScoreCard(unittest.TestCase):
    def test_to_dict(self):
        rs = RegretScore(
            source_count_penalty=0, downside_penalty=0,
            warranty_penalty=1.0, price_extreme_penalty=0,
            evidence_quality_penalty=0, total=1.0,
        )
        card = ScoreCard(
            evidence_score=18.0, confidence_score=6.0,
            price_score=2.0, reviews_score=0.75,
            regret_penalty=2.5, total=24.25,
            regret_detail=rs,
        )
        d = card.to_dict()
        self.assertEqual(d["evidence"], 18.0)
        self.assertEqual(d["regret_penalty"], 2.5)
        self.assertIn("regret_breakdown", d)
        self.assertEqual(d["regret_breakdown"]["no_warranty"], 1.0)


# ---------------------------------------------------------------------------
# target_audience_text
# ---------------------------------------------------------------------------


class TestTargetAudienceText(unittest.TestCase):
    def test_no_regret_pick(self):
        text = target_audience_text({}, "No-Regret Pick")
        self.assertTrue("reliable" in text.lower() or "overthinking" in text.lower())

    def test_best_value(self):
        text = target_audience_text({"amazon_price": "$49"}, "Best Value")
        self.assertTrue("budget" in text.lower() or "price" in text.lower())

    def test_best_upgrade(self):
        text = target_audience_text({}, "Best Upgrade")
        self.assertTrue("invest" in text.lower() or "premium" in text.lower())

    def test_specific_scenario_travel(self):
        text = target_audience_text(
            {"key_claims": ["Best for travel, lightweight and portable"]},
            "Best for Specific Scenario",
        )
        self.assertIn("travel", text.lower())


# ---------------------------------------------------------------------------
# publish_readiness_check
# ---------------------------------------------------------------------------


class TestPublishReadiness(unittest.TestCase):
    def test_empty_dir_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            pr = publish_readiness_check(Path(tmp))
            self.assertFalse(pr.passed)
            self.assertGreater(len(pr.failures), 0)

    def test_full_video_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # products.json
            inputs = root / "inputs"
            inputs.mkdir()
            products = {
                "products": [
                    {
                        "rank": i,
                        "name": f"Product {i}",
                        "affiliate_url": f"https://amzn.to/{i}",
                        "downside": "Minor issue",
                        "buy_this_if": "you want X",
                        "evidence": [{"source": "Wirecutter"}, {"source": "RTINGS"}],
                    }
                    for i in range(1, 6)
                ]
            }
            (inputs / "products.json").write_text(json.dumps(products))

            # script.txt (1200 words with disclosure)
            script_dir = root / "script"
            script_dir.mkdir()
            words = " ".join(["word"] * 1195)
            script = f"[HOOK]\n{words}\n[CONCLUSION]\naffiliate commission no extra cost"
            (script_dir / "script.txt").write_text(script)

            # audio chunks
            chunks = root / "audio" / "chunks"
            chunks.mkdir(parents=True)
            for i in range(5):
                (chunks / f"chunk_{i:02d}.mp3").write_bytes(b"\xff" * 100)

            # thumbnail
            assets = root / "assets"
            assets.mkdir()
            (assets / "thumbnail.png").write_bytes(b"\x89PNG" + b"\x00" * 60000)

            pr = publish_readiness_check(root)
            if not pr.passed:
                print(pr.summary())
            self.assertTrue(pr.passed)

    def test_missing_disclosure_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_dir = root / "script"
            script_dir.mkdir()
            words = " ".join(["word"] * 1200)
            (script_dir / "script.txt").write_text(f"[HOOK]\n{words}\n[CONCLUSION]\nThanks for watching")

            pr = publish_readiness_check(root, script_text=f"[HOOK]\n{words}\nThanks")
            disclosure_checks = [c for c in pr.checks if c.name == "FTC disclosure"]
            self.assertTrue(len(disclosure_checks) > 0)
            self.assertFalse(disclosure_checks[0].passed)

    def test_summary_format(self):
        pr = PublishReadiness(checks=[
            CheckItem("Test 1", True, "ok"),
            CheckItem("Test 2", False, "missing"),
        ])
        s = pr.summary()
        self.assertIn("NOT READY", s)
        self.assertIn("[PASS]", s)
        self.assertIn("[FAIL]", s)
