"""Tests for tools/agent_orchestrator.py.

Covers: MessageBus, QA gatekeeper, security agent, reviewer agent,
        agent protocol, run context, stage progression.
No browser/API calls — mocks external dependencies.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.agent_orchestrator import (
    ALLOWED_RESEARCH_DOMAINS,
    Message,
    MessageBus,
    MsgType,
    Orchestrator,
    QAGatekeeper,
    ReviewerAgent,
    RunContext,
    SecurityAgent,
    Stage,
    STAGE_ORDER,
    NicheStrategist,
    SEOAgent,
)
from tools.lib.video_paths import VideoPaths


class TestMessageBus(unittest.TestCase):
    """Test MessageBus inter-agent communication."""

    def test_post_and_get(self):
        bus = MessageBus()
        msg = Message(
            sender="agent_a", receiver="agent_b",
            msg_type=MsgType.INFO, stage=Stage.NICHE,
            content="hello",
        )
        bus.post(msg)
        self.assertEqual(bus.count, 1)

        msgs = bus.get_for("agent_b")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "hello")

    def test_broadcast(self):
        bus = MessageBus()
        bus.post(Message(
            sender="a", receiver="*",
            msg_type=MsgType.INFO, stage=Stage.NICHE,
            content="broadcast",
        ))
        # Any agent should receive broadcast
        self.assertEqual(len(bus.get_for("agent_x")), 1)
        self.assertEqual(len(bus.get_for("agent_y")), 1)

    def test_filter_by_type(self):
        bus = MessageBus()
        bus.post(Message("a", "*", MsgType.INFO, Stage.NICHE, "info"))
        bus.post(Message("a", "*", MsgType.ERROR, Stage.NICHE, "error"))
        bus.post(Message("a", "*", MsgType.INFO, Stage.RESEARCH, "info2"))

        errors = bus.get_by_type(MsgType.ERROR)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].content, "error")

    def test_filter_by_stage(self):
        bus = MessageBus()
        bus.post(Message("a", "*", MsgType.INFO, Stage.NICHE, "niche"))
        bus.post(Message("a", "*", MsgType.INFO, Stage.RESEARCH, "research"))

        niche_msgs = bus.get_all(stage=Stage.NICHE)
        self.assertEqual(len(niche_msgs), 1)
        self.assertEqual(niche_msgs[0].content, "niche")

    def test_to_log(self):
        bus = MessageBus()
        bus.post(Message("a", "b", MsgType.INFO, Stage.NICHE, "test"))
        log = bus.to_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["sender"], "a")
        self.assertEqual(log[0]["type"], "info")


class TestRunContext(unittest.TestCase):
    """Test RunContext initialization."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_default_paths(self):
        ctx = RunContext(video_id="test-001")
        self.assertIsInstance(ctx.paths, VideoPaths)
        self.assertEqual(ctx.paths.video_id, "test-001")

    def test_default_bus(self):
        ctx = RunContext(video_id="test-001")
        self.assertIsInstance(ctx.bus, MessageBus)
        self.assertEqual(ctx.bus.count, 0)

    def test_initial_state(self):
        ctx = RunContext(video_id="test-001", niche="wireless earbuds")
        self.assertEqual(ctx.niche, "wireless earbuds")
        self.assertFalse(ctx.aborted)
        self.assertEqual(ctx.stages_completed, [])
        self.assertEqual(ctx.errors, [])


class TestQAGatekeeper(unittest.TestCase):
    """Test QA Gatekeeper validation per stage."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.qa = QAGatekeeper()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_niche_gate_fail_no_niche(self):
        ctx = RunContext(video_id="test-001")
        passed, errors = self.qa.check_gate(ctx, Stage.NICHE)
        self.assertFalse(passed)
        self.assertTrue(any("No niche" in e for e in errors))

    def test_niche_gate_pass(self):
        ctx = RunContext(video_id="test-001", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        ctx.paths.niche_txt.write_text("wireless earbuds\n")
        passed, errors = self.qa.check_gate(ctx, Stage.NICHE)
        self.assertTrue(passed)
        self.assertEqual(errors, [])

    def test_research_gate_fail_no_shortlist(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("shortlist.json missing" in e for e in errors))

    def test_research_gate_fail_too_few(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [{"product_name": f"P{i}", "sources": []} for i in range(3)],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("minimum 5" in e for e in errors))

    def test_research_gate_domain_violation(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {
                    "product_name": f"P{i}",
                    "sources": [{"url": "https://www.nytimes.com/wirecutter/reviews/best-earbuds/"}],
                }
                for i in range(6)
            ] + [
                {
                    "product_name": "Bad",
                    "sources": [{"url": "https://sketchy-site.com/review"}],
                }
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("Domain violation" in e for e in errors))

    def test_research_gate_pass(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {
                    "product_name": f"Product {i}",
                    "reasons": ["good sound", "nice fit"],
                    "sources": [{"url": "https://www.nytimes.com/wirecutter/reviews/earbuds/"}],
                }
                for i in range(6)
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertTrue(passed)

    def test_rank_gate_fail_no_products(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertFalse(passed)

    def test_rank_gate_pass(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        products = [
            {
                "rank": i,
                "name": f"Product {i}",
                "asin": f"B0{i}XXXXX",
                "affiliate_url": f"https://amzn.to/{i}",
            }
            for i in range(1, 6)
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertTrue(passed)

    def test_rank_gate_pass_with_4_products(self):
        """4 products should pass the rank gate."""
        ctx = RunContext(video_id="test-001-4rank")
        ctx.paths.ensure_dirs()
        products = [
            {
                "rank": i,
                "name": f"Product {i}",
                "asin": f"B0{i}XXXXX",
                "affiliate_url": f"https://amzn.to/{i}",
            }
            for i in range(1, 5)
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertTrue(passed, f"Expected pass but got errors: {errors}")

    def test_rank_gate_fail_with_3_products(self):
        """3 products should fail the rank gate."""
        ctx = RunContext(video_id="test-001-3rank")
        ctx.paths.ensure_dirs()
        products = [
            {
                "rank": i,
                "name": f"Product {i}",
                "asin": f"B0{i}XXXXX",
                "affiliate_url": f"https://amzn.to/{i}",
            }
            for i in range(1, 4)
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertFalse(passed)
        self.assertTrue(any("4-5 products" in e for e in errors))

    def test_verify_gate_fail_too_few(self):
        """3 products should fail (minimum is 4)."""
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({
            "products": [{"product_name": f"P{i}"} for i in range(3)],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertFalse(passed)
        self.assertTrue(any("minimum 4" in e for e in errors))

    def test_verify_gate_pass_with_4_products(self):
        """4 products should pass with a warning."""
        ctx = RunContext(video_id="test-001-4prod")
        ctx.paths.ensure_dirs()
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({
            "products": [
                {"product_name": f"P{i}", "verification_method": "paapi",
                 "affiliate_short_url": ""}
                for i in range(4)
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertTrue(passed, f"Expected pass but got errors: {errors}")
        # Should have posted a WARNING info message
        warnings = [m for m in ctx.bus.get_by_type(MsgType.INFO)
                     if "WARNING" in m.content and "4 products" in m.content]
        self.assertTrue(len(warnings) > 0, "Expected warning about 4 products")

    def test_manifest_gate(self):
        import json as _json
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        # Fail without files
        passed, errors = self.qa.check_gate(ctx, Stage.MANIFEST)
        self.assertFalse(passed)
        # 3 missing manifest files + publish readiness failures
        manifest_errors = [e for e in errors if not e.startswith("Publish readiness")]
        self.assertEqual(len(manifest_errors), 3)

        # Pass with all required files (manifest + publish readiness artifacts)
        ctx.paths.resolve_dir.mkdir(parents=True, exist_ok=True)
        for f in ["edit_manifest.json", "markers.csv", "notes.md"]:
            (ctx.paths.resolve_dir / f).write_text("content")

        # Create products.json with 5 products
        inputs_dir = ctx.paths.root / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        products = {"products": [
            {"rank": i, "name": f"Product {i}",
             "affiliate_url": f"https://amzn.to/{i}",
             "downside": "Minor issue", "buy_this_if": "you want X",
             "evidence": [{"source": "Wirecutter"}, {"source": "RTINGS"}]}
            for i in range(1, 6)
        ]}
        (inputs_dir / "products.json").write_text(_json.dumps(products))

        # Create script with disclosure
        script_dir = ctx.paths.root / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        words = " ".join(["word"] * 1195)
        (script_dir / "script.txt").write_text(
            f"[HOOK]\n{words}\n[CONCLUSION]\naffiliate commission no extra cost"
        )

        # Create audio chunks
        chunks = ctx.paths.root / "audio" / "chunks"
        chunks.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            (chunks / f"chunk_{i:02d}.mp3").write_bytes(b"\xff" * 100)

        # Create thumbnail
        assets_dir = ctx.paths.root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "thumbnail.png").write_bytes(b"\x89PNG" + b"\x00" * 60000)

        passed, errors = self.qa.check_gate(ctx, Stage.MANIFEST)
        self.assertTrue(passed, f"Manifest gate should pass but got errors: {errors}")


class TestSecurityAgent(unittest.TestCase):
    """Test domain enforcement."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.security = SecurityAgent()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_clean_shortlist(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {"product_name": "P1", "sources": [{"url": "https://www.nytimes.com/wirecutter/test"}]},
                {"product_name": "P2", "sources": [{"url": "https://www.rtings.com/headphones/test"}]},
                {"product_name": "P3", "sources": [{"url": "https://www.pcmag.com/review"}]},
            ],
        }))
        violations = self.security.audit_research(ctx)
        self.assertEqual(violations, [])

    def test_unauthorized_domain(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {"product_name": "P1", "sources": [{"url": "https://www.nytimes.com/wirecutter/test"}]},
                {"product_name": "P2", "sources": [{"url": "https://random-blog.com/review"}]},
            ],
        }))
        violations = self.security.audit_research(ctx)
        self.assertTrue(len(violations) > 0)
        self.assertTrue(any("random-blog.com" in v for v in violations))

    def test_report_domain_check(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        report_path = ctx.paths.root / "inputs" / "research_report.md"
        report_path.write_text(
            "# Report\n"
            "Source: [Wirecutter](https://www.nytimes.com/wirecutter/test)\n"
            "Source: [Bad](https://unauthorized-site.com/review)\n"
        )
        violations = self.security.audit_research(ctx)
        self.assertTrue(any("unauthorized-site.com" in v for v in violations))


class TestReviewerAgent(unittest.TestCase):
    """Test reviewer agent audits."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.reviewer = ReviewerAgent()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_niche_review_pass(self):
        ctx = RunContext(video_id="test-001", niche="wireless earbuds")
        issues = self.reviewer.review_stage(ctx, Stage.NICHE)
        self.assertEqual(issues, [])

    def test_niche_review_fail(self):
        ctx = RunContext(video_id="test-001")
        issues = self.reviewer.review_stage(ctx, Stage.NICHE)
        self.assertTrue(any("No niche" in i for i in issues))

    def test_research_review_no_files(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        issues = self.reviewer.review_stage(ctx, Stage.RESEARCH)
        self.assertTrue(any("shortlist.json not produced" in i for i in issues))

    def test_rank_review_brand_diversity(self):
        ctx = RunContext(video_id="test-001", niche="earbuds")
        ctx.paths.ensure_dirs()
        # 3 products from same brand = low diversity warning
        products = [
            {"rank": i, "name": f"Sony WF-{i}", "brand": "Sony", "asin": f"B0{i}"}
            for i in range(1, 4)
        ] + [
            {"rank": 4, "name": "Jabra Elite", "brand": "Jabra", "asin": "B04"},
            {"rank": 5, "name": "AirPods Pro", "brand": "Apple", "asin": "B05"},
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        issues = self.reviewer.review_stage(ctx, Stage.RANK)
        self.assertTrue(any("diversity" in i.lower() for i in issues))


class TestNicheStrategist(unittest.TestCase):
    """Test niche strategist agent."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_provided_niche(self):
        ctx = RunContext(video_id="test-001", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        agent = NicheStrategist()
        ok = agent.run(ctx)
        self.assertTrue(ok)
        self.assertEqual(ctx.niche, "wireless earbuds")
        self.assertTrue(ctx.paths.niche_txt.is_file())

    def test_loaded_from_file(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        ctx.paths.niche_txt.write_text("robot vacuums\n")
        agent = NicheStrategist()
        ok = agent.run(ctx)
        self.assertTrue(ok)
        self.assertEqual(ctx.niche, "robot vacuums")

    @patch("tools.niche_picker.pick_niche")
    @patch("tools.niche_picker.update_history")
    def test_auto_pick(self, mock_update, mock_pick):
        from tools.niche_picker import NicheCandidate
        mock_pick.return_value = NicheCandidate("air purifiers", "home")
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        agent = NicheStrategist()
        ok = agent.run(ctx)
        self.assertTrue(ok)
        self.assertEqual(ctx.niche, "air purifiers")
        mock_update.assert_called_once()


class TestSEOAgent(unittest.TestCase):
    """Test SEO agent (placeholder)."""

    def test_always_passes(self):
        ctx = RunContext(video_id="test-001", niche="wireless earbuds")
        agent = SEOAgent()
        ok = agent.run(ctx)
        self.assertTrue(ok)
        # Should have posted an INFO message
        msgs = ctx.bus.get_by_type(MsgType.INFO)
        self.assertTrue(len(msgs) > 0)


class TestOrchestratorAgentRegistry(unittest.TestCase):
    """Test orchestrator initialization and agent registry."""

    def test_all_12_agents_registered(self):
        orch = Orchestrator()
        self.assertEqual(len(orch.agents), 12)

    def test_agent_names(self):
        orch = Orchestrator()
        expected = {
            "niche_strategist", "seo_agent", "research_agent",
            "amazon_verify", "top5_ranker", "script_producer",
            "dzine_asset_agent", "tts_agent", "resolve_packager",
            "qa_gatekeeper", "security_agent", "reviewer_agent",
        }
        self.assertEqual(set(orch.agents.keys()), expected)

    def test_list_agents(self):
        orch = Orchestrator()
        agents = orch.list_agents()
        self.assertEqual(len(agents), 12)
        for a in agents:
            self.assertIn("name", a)
            self.assertIn("role", a)
            self.assertTrue(len(a["role"]) > 5)


class TestStageOrder(unittest.TestCase):
    """Test stage ordering."""

    def test_stage_count(self):
        self.assertEqual(len(STAGE_ORDER), 8)

    def test_stage_order(self):
        stages = [s.value for s in STAGE_ORDER]
        self.assertEqual(stages, [
            "niche", "research", "verify", "rank",
            "script", "assets", "tts", "manifest",
        ])


class TestOrchestratorDryRun(unittest.TestCase):
    """Test orchestrator dry-run mode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    @patch("tools.lib.pipeline_status.VIDEOS_BASE")
    @patch("tools.lib.notify.send_telegram", return_value=True)
    def test_dry_run_niche_only(self, mock_telegram, mock_vbase):
        mock_vbase.__truediv__ = lambda self, x: Path(self.tmp.name) / x if hasattr(self, 'tmp') else Path("/tmp") / x
        orch = Orchestrator()
        ctx = orch.run_pipeline(
            "test-dry-001",
            niche="wireless earbuds",
            stop_after=Stage.NICHE,
            dry_run=True,
        )
        self.assertIn(Stage.NICHE, ctx.stages_completed)
        self.assertFalse(ctx.aborted)
        self.assertTrue(ctx.bus.count > 0)


class TestMessageTypes(unittest.TestCase):
    """Test message type enum."""

    def test_all_types(self):
        types = [t.value for t in MsgType]
        self.assertIn("info", types)
        self.assertIn("review", types)
        self.assertIn("question", types)
        self.assertIn("decision", types)
        self.assertIn("error", types)
        self.assertIn("gate_pass", types)
        self.assertIn("gate_fail", types)

    def test_message_timestamp(self):
        msg = Message("a", "b", MsgType.INFO, Stage.NICHE, "test")
        self.assertTrue(len(msg.timestamp) > 0)


class TestQAGatekeeperSubcategoryDrift(unittest.TestCase):
    """QA gate must HARD FAIL on any subcategory drift."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.qa = QAGatekeeper()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _write_contract(self, ctx):
        from tools.lib.subcategory_contract import SubcategoryContract, write_contract
        c = SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            allowed_subcategory_labels=["earbuds", "tws"],
            disallowed_labels=["headphone", "over-ear", "on-ear", "speaker", "soundbar"],
            allowed_keywords=["earbuds", "earbud"],
            disallowed_keywords=["headphone", "speaker", "soundbar"],
            mandatory_keywords=["earbuds", "earbud"],
            acceptance_test={
                "name_must_not_contain": ["headphone", "over-ear", "on-ear",
                                          "speaker", "soundbar"],
                "brand_is_not_product_name": True,
            },
        )
        write_contract(c, ctx.paths.subcategory_contract)

    def test_rank_gate_hard_fail_on_drift(self):
        """products.json with a drifted product must HARD FAIL the rank gate."""
        ctx = RunContext(video_id="test-drift-rank", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        self._write_contract(ctx)
        products = [
            {"rank": 1, "name": "Sony WF-1000XM5 Earbuds", "brand": "Sony", "asin": "B01"},
            {"rank": 2, "name": "Apple AirPods Pro Earbuds", "brand": "Apple", "asin": "B02"},
            {"rank": 3, "name": "Sony WH-1000XM5 Headphones", "brand": "Sony", "asin": "B03"},
            {"rank": 4, "name": "Jabra Elite 85t Earbuds", "brand": "Jabra", "asin": "B04"},
            {"rank": 5, "name": "Samsung Galaxy Buds Earbuds", "brand": "Samsung", "asin": "B05"},
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertFalse(passed)
        self.assertTrue(any("Subcategory drift" in e for e in errors))
        self.assertTrue(any("Headphones" in e for e in errors))

    def test_rank_gate_pass_all_on_subcategory(self):
        """products.json with all matching products passes the rank gate."""
        ctx = RunContext(video_id="test-drift-ok", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        self._write_contract(ctx)
        products = [
            {"rank": i, "name": f"Brand{i} Wireless Earbuds", "brand": f"Brand{i}",
             "asin": f"B0{i}", "affiliate_url": f"https://amzn.to/{i}"}
            for i in range(1, 6)
        ]
        ctx.paths.products_json.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertTrue(passed, f"Expected pass but got errors: {errors}")

    def test_verify_gate_hard_fail_on_drift(self):
        """verified.json with a drifted product must HARD FAIL the verify gate."""
        ctx = RunContext(video_id="test-drift-verify", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        self._write_contract(ctx)
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        products = [
            {"product_name": f"Brand{i} True Wireless Earbuds", "brand": f"Brand{i}"}
            for i in range(5)
        ] + [
            {"product_name": "Bose Smart Soundbar 600", "brand": "Bose"},
        ]
        verified_path.write_text(json.dumps({"products": products}))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertFalse(passed)
        self.assertTrue(any("Subcategory drift" in e for e in errors))

    def test_research_gate_hard_fail_on_drift(self):
        """shortlist.json with a drifted product must HARD FAIL the research gate."""
        ctx = RunContext(video_id="test-drift-research", niche="wireless earbuds")
        ctx.paths.ensure_dirs()
        self._write_contract(ctx)
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist = [
            {"product_name": f"Brand{i} Wireless Earbuds", "brand": f"Brand{i}",
             "sources": [{"url": "https://www.nytimes.com/wirecutter/test"}]}
            for i in range(5)
        ] + [
            {"product_name": "Sony WH-1000XM5 Headphones", "brand": "Sony",
             "sources": [{"url": "https://www.nytimes.com/wirecutter/test"}]},
        ]
        shortlist_path.write_text(json.dumps({"shortlist": shortlist}))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("Subcategory drift" in e for e in errors))


class TestQAResearchEvidence(unittest.TestCase):
    """QA gate checks evidence quality in shortlist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.qa = QAGatekeeper()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_qa_research_no_evidence_fails(self):
        """Shortlist item with no reasons triggers gate fail."""
        ctx = RunContext(video_id="test-evidence", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {"product_name": f"Product {i}", "reasons": ["good sound", "nice fit"],
                 "sources": [{"url": "https://nytimes.com/wirecutter/test"}]}
                for i in range(5)
            ] + [
                {"product_name": "No Evidence Product", "reasons": [],
                 "sources": [{"url": "https://nytimes.com/wirecutter/test"}]},
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("no evidence claims" in e for e in errors))

    def test_qa_research_with_evidence_passes(self):
        """All items with reasons passes the evidence check."""
        ctx = RunContext(video_id="test-evidence-ok", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [
                {"product_name": f"Product {i}", "reasons": ["good"],
                 "sources": [{"url": "https://nytimes.com/wirecutter/test"}]}
                for i in range(6)
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertTrue(passed, f"Expected pass but got errors: {errors}")


class TestQAVerifySiteStripe(unittest.TestCase):
    """QA gate checks SiteStripe short links for browser-verified products."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.qa = QAGatekeeper()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_qa_verify_missing_sitestripe_fails(self):
        """Browser-verified product without short_url triggers error."""
        ctx = RunContext(video_id="test-sitestripe", niche="earbuds")
        ctx.paths.ensure_dirs()
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({
            "products": [
                {"product_name": f"Product {i}", "verification_method": "browser",
                 "affiliate_short_url": f"https://amzn.to/{i}"}
                for i in range(4)
            ] + [
                {"product_name": "Missing Link", "verification_method": "browser",
                 "affiliate_short_url": ""},
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertTrue(any("SiteStripe" in e for e in errors))

    def test_qa_verify_paapi_no_sitestripe_ok(self):
        """PA-API products skip SiteStripe check."""
        ctx = RunContext(video_id="test-paapi", niche="earbuds")
        ctx.paths.ensure_dirs()
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({
            "products": [
                {"product_name": f"Product {i}", "verification_method": "paapi",
                 "affiliate_short_url": ""}
                for i in range(5)
            ],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        # No SiteStripe error for PA-API products
        sitestripe_errors = [e for e in errors if "SiteStripe" in e]
        self.assertEqual(sitestripe_errors, [])


class TestVerifyRetry(unittest.TestCase):
    """Verify retry logic when <5 products verify."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    @patch("tools.agent_orchestrator.time.sleep")
    @patch("tools.amazon_verify.verify_products")
    @patch("tools.amazon_verify.write_verified")
    def test_verify_retry_on_insufficient(self, mock_write, mock_verify, mock_sleep):
        """When first pass returns 3, retry returns 2 more -> total 5."""
        from tools.agent_orchestrator import AmazonVerifyAgent

        # Create mock verified objects
        class MockVerified:
            def __init__(self, name):
                self.product_name = name

        first_pass = [MockVerified(f"Product {i}") for i in range(3)]
        retry_pass = [MockVerified(f"Product {i}") for i in range(3, 5)]
        mock_verify.side_effect = [first_pass, retry_pass]

        ctx = RunContext(video_id="test-retry", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [{"product_name": f"Product {i}"} for i in range(7)],
        }))

        agent = AmazonVerifyAgent()
        agent.run(ctx)

        # verify_products called twice (initial + retry)
        self.assertEqual(mock_verify.call_count, 2)

    @patch("tools.amazon_verify.verify_products")
    @patch("tools.amazon_verify.write_verified")
    def test_verify_no_retry_when_sufficient(self, mock_write, mock_verify):
        """When first pass returns 5, no retry needed."""
        from tools.agent_orchestrator import AmazonVerifyAgent

        class MockVerified:
            def __init__(self, name):
                self.product_name = name

        mock_verify.return_value = [MockVerified(f"Product {i}") for i in range(5)]

        ctx = RunContext(video_id="test-no-retry", niche="earbuds")
        ctx.paths.ensure_dirs()
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        shortlist_path.write_text(json.dumps({
            "shortlist": [{"product_name": f"Product {i}"} for i in range(7)],
        }))

        agent = AmazonVerifyAgent()
        agent.run(ctx)

        # verify_products called only once
        self.assertEqual(mock_verify.call_count, 1)


class TestAllowedDomains(unittest.TestCase):
    """Test domain enforcement constants."""

    def test_exactly_3_domains(self):
        self.assertEqual(len(ALLOWED_RESEARCH_DOMAINS), 3)

    def test_domain_contents(self):
        self.assertIn("nytimes.com", ALLOWED_RESEARCH_DOMAINS)
        self.assertIn("rtings.com", ALLOWED_RESEARCH_DOMAINS)
        self.assertIn("pcmag.com", ALLOWED_RESEARCH_DOMAINS)


class TestPriceFloor(unittest.TestCase):
    """Test price floor enforcement in QA gates."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.qa = QAGatekeeper()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _make_verified(self, ctx, products):
        """Write verified.json with the given product list."""
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({"products": products}))

    def _make_products(self, ctx, products):
        """Write products.json with the given product list."""
        ctx.paths.products_json.write_text(json.dumps({"products": products}))

    def _write_micro_niche(self, ctx, price_min=120):
        """Write micro_niche.json with given price_min."""
        ctx.paths.micro_niche_json.write_text(json.dumps({
            "subcategory": "test",
            "buyer_pain": "test",
            "intent_phrase": "test",
            "price_min": price_min,
            "price_max": 300,
        }))

    def test_price_floor_verify_hard_fail(self):
        """Product at $89 with price_min=120 triggers error."""
        ctx = RunContext(video_id="test-pf-fail", niche="test")
        ctx.paths.ensure_dirs()
        self._write_micro_niche(ctx, price_min=120)
        self._make_verified(ctx, [
            {"product_name": f"Product {i}", "brand": "B", "amazon_price": "$149.99",
             "verification_method": "api", "affiliate_short_url": ""}
            for i in range(4)
        ] + [
            {"product_name": "Cheap Product", "brand": "B", "amazon_price": "$89.00",
             "verification_method": "api", "affiliate_short_url": ""},
        ])
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertFalse(passed)
        self.assertTrue(any("Price floor" in e for e in errors))

    def test_price_floor_verify_pass(self):
        """Product at $149 with price_min=120 passes."""
        ctx = RunContext(video_id="test-pf-pass", niche="test")
        ctx.paths.ensure_dirs()
        self._write_micro_niche(ctx, price_min=120)
        self._make_verified(ctx, [
            {"product_name": f"Product {i}", "brand": "B", "amazon_price": "$149.99",
             "verification_method": "api", "affiliate_short_url": ""}
            for i in range(5)
        ])
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertTrue(passed, f"Unexpected errors: {errors}")

    def test_price_floor_respects_micro_niche(self):
        """Uses micro_niche.json price_min if present (lower floor)."""
        ctx = RunContext(video_id="test-pf-mn", niche="test")
        ctx.paths.ensure_dirs()
        self._write_micro_niche(ctx, price_min=50)  # lower floor
        self._make_verified(ctx, [
            {"product_name": f"Product {i}", "brand": "B", "amazon_price": "$79.99",
             "verification_method": "api", "affiliate_short_url": ""}
            for i in range(5)
        ])
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        # $79.99 >= $50, so should pass
        self.assertTrue(passed, f"Unexpected errors: {errors}")

    def test_price_floor_rank_hard_fail(self):
        """Price floor also enforced at rank stage."""
        ctx = RunContext(video_id="test-pf-rank", niche="test")
        ctx.paths.ensure_dirs()
        self._write_micro_niche(ctx, price_min=120)
        self._make_products(ctx, [
            {"rank": i, "name": f"Product {i}", "brand": "B", "price": "$149.99",
             "asin": f"B00{i}", "affiliate_url": f"https://amzn.to/{i}"}
            for i in range(1, 5)
        ] + [
            {"rank": 5, "name": "Cheap One", "brand": "B", "price": "$49.99",
             "asin": "B005", "affiliate_url": "https://amzn.to/5"},
        ])
        passed, errors = self.qa.check_gate(ctx, Stage.RANK)
        self.assertFalse(passed)
        self.assertTrue(any("Price floor" in e for e in errors))

    def test_price_floor_default_when_no_micro_niche(self):
        """Without micro_niche.json, uses DEFAULT_PRICE_FLOOR."""
        from tools.agent_orchestrator import DEFAULT_PRICE_FLOOR
        ctx = RunContext(video_id="test-pf-default", niche="test")
        ctx.paths.ensure_dirs()
        # No micro_niche.json written
        self._make_verified(ctx, [
            {"product_name": f"Product {i}", "brand": "B", "amazon_price": "$99.00",
             "verification_method": "api", "affiliate_short_url": ""}
            for i in range(5)
        ])
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        # $99 < $120 default, should fail
        self.assertFalse(passed)
        self.assertTrue(any("Price floor" in e for e in errors))


class TestSupabaseRunId(unittest.TestCase):
    """Test Supabase run_id propagation in orchestrator."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    @patch("tools.lib.supabase_pipeline.insert")
    def test_run_id_set_on_context(self, mock_insert):
        """create_run returns UUID, stored in ctx.run_id."""
        mock_insert.return_value = {"id": "abc-uuid-123"}
        from tools.lib.supabase_pipeline import create_run
        run_id = create_run("test-001", "wireless earbuds")
        self.assertEqual(run_id, "abc-uuid-123")

    @patch.dict("os.environ", {}, clear=True)
    def test_run_id_empty_when_disabled(self):
        """No crash, returns empty when Supabase disabled."""
        from tools.lib.supabase_pipeline import create_run
        run_id = create_run("test-001", "earbuds")
        self.assertEqual(run_id, "")

    @patch("tools.lib.supabase_pipeline.insert")
    def test_events_persisted_when_run_id_set(self, mock_insert):
        """MessageBus.post calls log_event when run_id is set."""
        bus = MessageBus()
        bus.set_run_id("test-run-id")
        bus.post(Message("agent_a", "agent_b", MsgType.INFO, Stage.NICHE, "hello"))
        # log_event should have called insert with agent_events
        calls = [c for c in mock_insert.call_args_list if c[0][0] == "agent_events"]
        self.assertTrue(len(calls) > 0)
        payload = calls[0][0][1]
        self.assertEqual(payload["run_id"], "test-run-id")
        self.assertEqual(payload["agent_name"], "agent_a")

    def test_events_not_persisted_without_run_id(self):
        """No supabase calls when run_id is empty."""
        bus = MessageBus()
        # No set_run_id called — _run_id stays ""
        with patch("tools.lib.supabase_pipeline.insert") as mock_insert:
            bus.post(Message("agent_a", "*", MsgType.INFO, Stage.NICHE, "test"))
            # insert should NOT be called for agent_events
            event_calls = [c for c in mock_insert.call_args_list if c[0][0] == "agent_events"]
            self.assertEqual(len(event_calls), 0)


class TestRunContextRunId(unittest.TestCase):
    """Test run_id field on RunContext."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_run_id_default_empty(self):
        ctx = RunContext(video_id="test-001")
        self.assertEqual(ctx.run_id, "")


class TestPreflightInOrchestrator(unittest.TestCase):
    """Test preflight checks in orchestrator run_pipeline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    @patch("tools.lib.pipeline_status.VIDEOS_BASE")
    @patch("tools.lib.notify.send_telegram", return_value=True)
    @patch("tools.lib.preflight.preflight_check")
    def test_preflight_fail_aborts_pipeline(self, mock_pf, mock_telegram, mock_vbase):
        """Preflight failure on verify stage should abort the pipeline."""
        from tools.lib.preflight import PreflightResult
        mock_pf.return_value = PreflightResult(
            passed=False,
            failures=["Not logged in to Amazon. Log in at https://www.amazon.com/gp/css/homepage.html"],
        )

        orch = Orchestrator()
        # Start at verify stage to trigger preflight
        ctx = orch.run_pipeline(
            "test-pf-fail",
            niche="wireless earbuds",
            start_stage=Stage.VERIFY,
        )
        self.assertTrue(ctx.aborted)
        self.assertIn("Preflight", ctx.abort_reason)

    @patch("tools.lib.pipeline_status.VIDEOS_BASE")
    @patch("tools.lib.notify.send_telegram", return_value=True)
    @patch("tools.lib.preflight.preflight_check")
    def test_preflight_pass_continues(self, mock_pf, mock_telegram, mock_vbase):
        """Preflight pass should let the stage proceed normally."""
        from tools.lib.preflight import PreflightResult
        mock_pf.return_value = PreflightResult(passed=True)

        orch = Orchestrator()
        # Niche stage has no preflight → passes
        ctx = orch.run_pipeline(
            "test-pf-pass",
            niche="wireless earbuds",
            stop_after=Stage.NICHE,
            dry_run=True,
        )
        self.assertFalse(ctx.aborted)
        self.assertIn(Stage.NICHE, ctx.stages_completed)


class TestAmazonBlockError(unittest.TestCase):
    """Test _AmazonBlockError classification."""

    def test_block_error_classified_as_session(self):
        from tools.amazon_verify import _AmazonBlockError
        from tools.lib.retry import classify_error, ErrorKind
        err = _AmazonBlockError("Amazon CAPTCHA / bot-detection block")
        self.assertEqual(classify_error(err), ErrorKind.SESSION)


if __name__ == "__main__":
    unittest.main()
