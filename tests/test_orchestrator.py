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
            "shortlist": [{"product_name": f"P{i}", "sources": []} for i in range(5)],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.RESEARCH)
        self.assertFalse(passed)
        self.assertTrue(any("minimum 8" in e for e in errors))

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
                for i in range(10)
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
                    "sources": [{"url": "https://www.nytimes.com/wirecutter/reviews/earbuds/"}],
                }
                for i in range(10)
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

    def test_verify_gate_fail_too_few(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        verified_path.write_text(json.dumps({
            "products": [{"product_name": f"P{i}"} for i in range(3)],
        }))
        passed, errors = self.qa.check_gate(ctx, Stage.VERIFY)
        self.assertFalse(passed)
        self.assertTrue(any("minimum 5" in e for e in errors))

    def test_manifest_gate(self):
        ctx = RunContext(video_id="test-001")
        ctx.paths.ensure_dirs()
        # Fail without files
        passed, errors = self.qa.check_gate(ctx, Stage.MANIFEST)
        self.assertFalse(passed)
        self.assertEqual(len(errors), 3)  # 3 missing files

        # Pass with files
        ctx.paths.resolve_dir.mkdir(parents=True, exist_ok=True)
        for f in ["edit_manifest.json", "markers.csv", "notes.md"]:
            (ctx.paths.resolve_dir / f).write_text("content")
        passed, errors = self.qa.check_gate(ctx, Stage.MANIFEST)
        self.assertTrue(passed)


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


class TestAllowedDomains(unittest.TestCase):
    """Test domain enforcement constants."""

    def test_exactly_3_domains(self):
        self.assertEqual(len(ALLOWED_RESEARCH_DOMAINS), 3)

    def test_domain_contents(self):
        self.assertIn("nytimes.com", ALLOWED_RESEARCH_DOMAINS)
        self.assertIn("rtings.com", ALLOWED_RESEARCH_DOMAINS)
        self.assertIn("pcmag.com", ALLOWED_RESEARCH_DOMAINS)


if __name__ == "__main__":
    unittest.main()
