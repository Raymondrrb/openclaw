"""Tests for research agent shortlist capping and subcategory filtering.

No browser/API calls — all pure logic or mocked.
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.research_agent import (
    AggregatedProduct,
    ProductEvidence,
    _build_shortlist,
)


def _make_agg(
    name: str,
    brand: str = "Brand",
    source_count: int = 1,
    evidence_score: float = 1.0,
    label: str = "",
) -> AggregatedProduct:
    """Helper to create AggregatedProduct for testing."""
    evidence = [
        ProductEvidence(
            product_name=name,
            brand=brand,
            source_name=f"Source{i+1}",
            source_url=f"https://nytimes.com/wirecutter/{i}",
        )
        for i in range(source_count)
    ]
    return AggregatedProduct(
        product_name=name,
        brand=brand,
        evidence=evidence,
        source_count=source_count,
        evidence_score=evidence_score,
        primary_label=label,
        all_labels=[label] if label else [],
    )


class TestBuildShortlistCap(unittest.TestCase):
    """Shortlist should never exceed 7 and minimum is 5."""

    def test_shortlist_max_7(self):
        """Even with 20 multi-source products, cap at 7."""
        aggregated = [
            _make_agg(f"Product {i}", source_count=2, evidence_score=5.0)
            for i in range(20)
        ]
        shortlist, rejected = _build_shortlist(aggregated)
        self.assertLessEqual(len(shortlist), 7)
        self.assertGreater(len(rejected), 0)

    def test_shortlist_min_5_relaxation(self):
        """If fewer than 5 qualify, promote from rejected."""
        # 3 multi-source + 10 single-source low-evidence
        aggregated = [
            _make_agg(f"Good {i}", source_count=2, evidence_score=5.0)
            for i in range(3)
        ] + [
            _make_agg(f"Weak {i}", source_count=1, evidence_score=0.5)
            for i in range(10)
        ]
        shortlist, rejected = _build_shortlist(aggregated)
        self.assertGreaterEqual(len(shortlist), 5)
        self.assertLessEqual(len(shortlist), 7)

    def test_shortlist_exact_5(self):
        """5 good products should stay at 5."""
        aggregated = [
            _make_agg(f"Product {i}", source_count=2, evidence_score=5.0)
            for i in range(5)
        ]
        shortlist, rejected = _build_shortlist(aggregated)
        self.assertEqual(len(shortlist), 5)
        self.assertEqual(len(rejected), 0)

    def test_shortlist_top_picks_included(self):
        """Single-source 'top pick' products make the shortlist."""
        aggregated = [
            _make_agg("Winner", source_count=1, evidence_score=1.5, label="top pick"),
        ]
        shortlist, rejected = _build_shortlist(aggregated)
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].product_name, "Winner")


class TestSubcategoryFilter(unittest.TestCase):
    """Products failing the subcategory gate should be excluded."""

    def test_subcategory_filter_rejects_drift(self):
        from tools.lib.subcategory_contract import SubcategoryContract, passes_gate

        contract = SubcategoryContract(
            niche_name="carry on luggage",
            category="travel",
            allowed_keywords=["luggage", "suitcase", "carry-on", "carry on"],
            disallowed_keywords=["headphone", "camera", "earbuds"],
            mandatory_keywords=["luggage", "suitcase", "carry-on"],
        )

        products = [
            _make_agg("Samsonite Freeform Carry-On Luggage", "Samsonite", source_count=2),
            _make_agg("Sony WH-1000XM5 Headphones", "Sony", source_count=2),
            _make_agg("Away The Carry-On Suitcase", "Away", source_count=2),
            _make_agg("Canon EOS R6 Camera", "Canon", source_count=1),
        ]

        filtered = []
        for agg in products:
            ok, _ = passes_gate(agg.product_name, agg.brand, contract)
            if ok:
                filtered.append(agg)

        self.assertEqual(len(filtered), 2)
        names = [f.product_name for f in filtered]
        self.assertIn("Samsonite Freeform Carry-On Luggage", names)
        self.assertIn("Away The Carry-On Suitcase", names)
        self.assertNotIn("Sony WH-1000XM5 Headphones", names)
        self.assertNotIn("Canon EOS R6 Camera", names)

    def test_all_shortlist_pass_contract(self):
        """After filtering, shortlist should be <= 7 and all pass gate."""
        from tools.lib.subcategory_contract import SubcategoryContract, passes_gate

        contract = SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            allowed_keywords=["earbuds", "earbud", "in-ear"],
            disallowed_keywords=["headphone", "speaker"],
            mandatory_keywords=["earbuds", "earbud"],
        )

        products = [
            _make_agg(f"Brand{i} Wireless Earbuds V{i}", f"Brand{i}", source_count=2, evidence_score=4.0)
            for i in range(10)
        ]

        filtered = [a for a in products if passes_gate(a.product_name, a.brand, contract)[0]]
        shortlist, _ = _build_shortlist(filtered)

        self.assertLessEqual(len(shortlist), 7)
        for item in shortlist:
            ok, _ = passes_gate(item.product_name, item.brand, contract)
            self.assertTrue(ok)


class TestTop5ContractEnforcement(unittest.TestCase):
    """select_top5 must reject drifted products when contract is provided."""

    def test_select_top5_rejects_drifted(self):
        import json
        import tempfile
        from tools.lib.subcategory_contract import SubcategoryContract, write_contract
        from tools.top5_ranker import select_top5

        contract = SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            allowed_keywords=["earbuds", "earbud"],
            disallowed_keywords=["headphone", "speaker"],
            mandatory_keywords=["earbuds", "earbud"],
            acceptance_test={
                "name_must_contain_one_of": ["earbuds", "earbud"],
                "name_must_not_contain": ["headphone", "speaker"],
                "brand_is_not_product_name": True,
            },
        )

        verified = [
            {"product_name": f"Brand{i} Wireless Earbuds", "brand": f"Brand{i}",
             "evidence": [], "key_claims": [], "match_confidence": "high"}
            for i in range(6)
        ] + [
            {"product_name": "Sony WH-1000XM5 Headphones", "brand": "Sony",
             "evidence": [], "key_claims": [], "match_confidence": "high"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "contract.json"
            write_contract(contract, cp)
            top5 = select_top5(verified, contract_path=cp)

        names = [p.get("product_name", "") for p in top5]
        self.assertNotIn("Sony WH-1000XM5 Headphones", names)
        self.assertEqual(len(top5), 5)
        for p in top5:
            self.assertIn("earbuds", p["product_name"].lower())

    def test_select_top5_no_contract_no_filter(self):
        """Without contract_path, all products pass through."""
        from tools.top5_ranker import select_top5

        verified = [
            {"product_name": f"Product {i}", "brand": f"Brand{i}",
             "evidence": [], "key_claims": [], "match_confidence": "high"}
            for i in range(5)
        ]
        top5 = select_top5(verified)
        self.assertEqual(len(top5), 5)


class TestComparisonPageDetection(unittest.TestCase):
    """_is_comparison_page rejects non-comparison URLs."""

    def test_comparison_page_detected(self):
        from tools.research_agent import _is_comparison_page
        self.assertTrue(_is_comparison_page(
            "The Best Wireless Earbuds for 2026", "https://www.nytimes.com/wirecutter/reviews/best-wireless-earbuds/"))
        self.assertTrue(_is_comparison_page(
            "Top 5 Noise Cancelling Headphones", "https://www.rtings.com/headphones/reviews/best"))

    def test_non_comparison_rejected(self):
        from tools.research_agent import _is_comparison_page
        # "How to" articles are not comparison pages
        self.assertFalse(_is_comparison_page(
            "How to Choose Headphones", "https://www.pcmag.com/how-to/choose-headphones"))
        # News articles are not comparison pages
        self.assertFalse(_is_comparison_page(
            "Sony Announces New XM6 Headphones", "https://www.pcmag.com/news/sony-xm6"))


class TestExtractModel(unittest.TestCase):
    """Model extraction from product name."""

    def test_extract_model_strips_brand(self):
        from tools.research_agent import _extract_model
        self.assertEqual(_extract_model("Sony WH-1000XM5", "Sony"), "WH-1000XM5")

    def test_extract_model_no_brand(self):
        from tools.research_agent import _extract_model
        self.assertEqual(_extract_model("WH-1000XM5", ""), "WH-1000XM5")

    def test_extract_model_brand_only(self):
        from tools.research_agent import _extract_model
        self.assertEqual(_extract_model("Sony", "Sony"), "Sony")


class TestWhyInShortlist(unittest.TestCase):
    """Auto-generated shortlist reason."""

    def test_why_multi_source(self):
        from tools.research_agent import _why_in_shortlist
        agg = _make_agg("Test Product", source_count=2, evidence_score=5.0, label="best overall")
        reason = _why_in_shortlist(agg)
        self.assertIn("2 sources", reason)
        self.assertIn("best overall", reason)


class TestDownsideExtraction(unittest.TestCase):
    """_extract_downside() should find negative/con sentences."""

    def test_extract_downside_found(self):
        from tools.research_agent import _extract_downside
        lines = [
            "The Sony WF-1000XM5 is our top pick.",
            "Great sound quality and ANC performance.",
            "However, the case is larger than competitors.",
            "Battery life is solid at 8 hours.",
        ]
        result = _extract_downside(lines, 0, "Sony")
        self.assertIn("However", result)

    def test_extract_downside_none(self):
        from tools.research_agent import _extract_downside
        lines = [
            "The Sony WF-1000XM5 is our top pick.",
            "Great sound quality and ANC performance.",
            "Battery life is solid at 8 hours.",
        ]
        result = _extract_downside(lines, 0, "Sony")
        self.assertEqual(result, "")

    def test_extract_downside_expensive(self):
        from tools.research_agent import _extract_downside
        lines = [
            "The product is our pick.",
            "The sound is amazing.",
            "It is quite expensive compared to others.",
        ]
        result = _extract_downside(lines, 0, "Sony")
        self.assertIn("expensive", result)


class TestShortlistJsonDownside(unittest.TestCase):
    """Serialized shortlist.json must include downside field."""

    def test_shortlist_json_has_downside_field(self):
        import json
        import tempfile
        from tools.research_agent import (
            ResearchReport, AggregatedProduct, ProductEvidence,
            _write_shortlist_json,
        )
        agg = AggregatedProduct(
            product_name="Test Earbuds",
            brand="Test",
            evidence=[ProductEvidence(
                product_name="Test Earbuds", brand="Test",
                source_name="Wirecutter",
                source_url="https://nytimes.com/wirecutter/test",
                downside="Case is bulky",
            )],
            source_count=1, evidence_score=3.0,
            all_downsides=["Case is bulky"],
            all_reasons=["Great sound"],
        )
        report = ResearchReport(niche="earbuds", shortlist=[agg])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "shortlist.json"
            _write_shortlist_json(report, out)
            data = json.loads(out.read_text())
            self.assertIn("downside", data["shortlist"][0])
            self.assertEqual(data["shortlist"][0]["downside"], "Case is bulky")


if __name__ == "__main__":
    unittest.main()
