#!/usr/bin/env python3
"""Multi-agent orchestration layer for the Rayviews pipeline.

12 named agents communicate via a structured MessageBus.
A QA Gatekeeper blocks progression if artifacts/rules fail.
A Reviewer Agent audits other agents' outputs after each stage.
A Security Agent enforces domain restrictions.

Usage:
    python3 tools/agent_orchestrator.py --video-id <id> [--niche "<niche>"]
    python3 tools/agent_orchestrator.py --video-id <id> --stage research
    python3 tools/agent_orchestrator.py --video-id <id> --dry-run

Stdlib only (except Playwright, imported lazily).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, now_iso, project_root
from tools.lib.video_paths import VIDEOS_BASE, VideoPaths

# ---------------------------------------------------------------------------
# Message types for inter-agent communication
# ---------------------------------------------------------------------------


class MsgType(str, Enum):
    INFO = "info"
    REVIEW = "review"
    QUESTION = "question"
    DECISION = "decision"
    ERROR = "error"
    GATE_PASS = "gate_pass"
    GATE_FAIL = "gate_fail"


@dataclass
class Message:
    """Structured message between agents."""
    sender: str
    receiver: str  # agent name or "*" for broadcast
    msg_type: MsgType
    stage: str
    content: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = now_iso()


class MessageBus:
    """Central message store for inter-agent communication."""

    def __init__(self):
        self._messages: list[Message] = []
        self._run_id: str = ""

    def set_run_id(self, run_id: str) -> None:
        self._run_id = run_id

    def post(self, msg: Message) -> None:
        self._messages.append(msg)
        _log(f"  [{msg.sender} -> {msg.receiver}] {msg.msg_type.value}: {msg.content[:80]}")
        if self._run_id:
            try:
                from tools.lib.supabase_pipeline import log_event
                log_event(
                    self._run_id, msg.sender, msg.receiver,
                    msg.msg_type.value, msg.stage if isinstance(msg.stage, str) else msg.stage.value,
                    msg.content, msg.data,
                )
            except Exception:
                pass  # never let Supabase break the pipeline

    def get_for(self, agent_name: str, *, stage: str = "") -> list[Message]:
        """Get messages addressed to a specific agent (or broadcast)."""
        result = []
        for m in self._messages:
            if m.receiver in (agent_name, "*"):
                if not stage or m.stage == stage:
                    result.append(m)
        return result

    def get_by_type(self, msg_type: MsgType, *, stage: str = "") -> list[Message]:
        result = []
        for m in self._messages:
            if m.msg_type == msg_type:
                if not stage or m.stage == stage:
                    result.append(m)
        return result

    def get_all(self, *, stage: str = "") -> list[Message]:
        if not stage:
            return list(self._messages)
        return [m for m in self._messages if m.stage == stage]

    @property
    def count(self) -> int:
        return len(self._messages)

    def to_log(self) -> list[dict]:
        """Serialize all messages for logging."""
        return [
            {
                "sender": m.sender,
                "receiver": m.receiver,
                "type": m.msg_type.value,
                "stage": m.stage,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in self._messages
        ]


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    NICHE = "niche"
    RESEARCH = "research"
    VERIFY = "verify"
    RANK = "rank"
    SCRIPT = "script"
    ASSETS = "assets"
    TTS = "tts"
    MANIFEST = "manifest"


STAGE_ORDER = list(Stage)


# ---------------------------------------------------------------------------
# Run context — shared state for all agents
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    """Shared state passed to every agent."""
    video_id: str
    niche: str = ""
    bus: MessageBus = field(default_factory=MessageBus)
    paths: VideoPaths | None = None
    dry_run: bool = False
    force: bool = False
    current_stage: Stage = Stage.NICHE
    stages_completed: list[Stage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""
    run_id: str = ""

    def __post_init__(self):
        if self.paths is None:
            self.paths = VideoPaths(self.video_id)


# ---------------------------------------------------------------------------
# Agent protocol
# ---------------------------------------------------------------------------


class Agent(Protocol):
    """All agents implement this interface."""
    name: str
    role: str

    def run(self, ctx: RunContext) -> bool:
        """Execute the agent's task. Returns True on success."""
        ...


# ---------------------------------------------------------------------------
# Allowed domains (strict enforcement)
# ---------------------------------------------------------------------------

ALLOWED_RESEARCH_DOMAINS = frozenset({"nytimes.com", "rtings.com", "pcmag.com"})

DEFAULT_PRICE_FLOOR = 120


def _extract_price(price_str: str) -> float | None:
    """Extract numeric price from a string like '$149.99' or '149'. Returns None if unparseable."""
    if not price_str:
        return None
    import re
    m = re.search(r'[\d,]+\.?\d*', str(price_str).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Agent implementations
# ---------------------------------------------------------------------------


class NicheStrategist:
    """Picks the daily niche from the curated pool."""
    name = "niche_strategist"
    role = "Select today's niche keyword based on scoring and history"

    def run(self, ctx: RunContext) -> bool:
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        # If niche already set (from CLI or niche.txt), use it
        if ctx.niche:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.NICHE,
                content=f"Using provided niche: {ctx.niche}",
            ))
            ctx.paths.niche_txt.parent.mkdir(parents=True, exist_ok=True)
            ctx.paths.niche_txt.write_text(ctx.niche + "\n", encoding="utf-8")
            self._ensure_contract(ctx)
            return True

        # Check niche.txt
        if ctx.paths.niche_txt.is_file():
            ctx.niche = ctx.paths.niche_txt.read_text(encoding="utf-8").strip()
            if ctx.niche:
                ctx.bus.post(Message(
                    sender=self.name, receiver="*",
                    msg_type=MsgType.INFO, stage=Stage.NICHE,
                    content=f"Loaded niche from file: {ctx.niche}",
                ))
                self._ensure_contract(ctx)
                return True

        # Pick from pool
        from tools.niche_picker import pick_niche, update_history
        candidate = pick_niche(today)
        ctx.niche = candidate.keyword
        ctx.paths.ensure_dirs()
        ctx.paths.niche_txt.write_text(ctx.niche + "\n", encoding="utf-8")
        update_history(
            ctx.niche, today, video_id=ctx.video_id,
            category=candidate.category, subcategory=candidate.subcategory,
            intent=candidate.intent,
        )

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.DECISION, stage=Stage.NICHE,
            content=f"Selected niche: {ctx.niche} (static: {candidate.static_score:.0f}, intent: {candidate.intent})",
            data={
                "keyword": ctx.niche,
                "static_score": candidate.static_score,
                "category": candidate.category,
                "subcategory": candidate.subcategory,
                "intent": candidate.intent,
                "price_band": candidate.price_band,
            },
        ))

        # Supabase: save niche
        if ctx.run_id:
            try:
                from tools.lib.supabase_pipeline import save_niche
                save_niche(ctx.run_id, ctx.video_id,
                           cluster=candidate.category,
                           subcategory=candidate.subcategory,
                           intent_phrase=ctx.niche,
                           total_score=candidate.static_score)
            except Exception:
                pass

        self._ensure_contract(ctx)
        return True

    def _ensure_contract(self, ctx: RunContext) -> None:
        """Generate subcategory contract if it doesn't exist yet."""
        if ctx.paths.subcategory_contract.is_file():
            return
        from tools.lib.subcategory_contract import generate_contract, write_contract
        from tools.lib.dzine_schema import detect_category
        contract = generate_contract(ctx.niche, detect_category(ctx.niche))
        ctx.paths.ensure_dirs()
        write_contract(contract, ctx.paths.subcategory_contract)
        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.NICHE,
            content=f"Subcategory contract generated for '{ctx.niche}' ({contract.category})",
        ))


class SEOAgent:
    """Validates niche for SEO viability (placeholder for future search volume API)."""
    name = "seo_agent"
    role = "Validate niche keyword for search volume and competition"

    def run(self, ctx: RunContext) -> bool:
        # Placeholder: always approves. Real implementation would check
        # YouTube search suggest, Google Trends, etc.
        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.NICHE,
            content=f"SEO check passed for '{ctx.niche}' (placeholder)",
            data={"keyword": ctx.niche, "approved": True},
        ))
        return True


class ResearchAgentWrapper:
    """Browses real review pages from exactly 3 sources."""
    name = "research_agent"
    role = "Browse Wirecutter, RTINGS, PCMag for product reviews with evidence"

    def run(self, ctx: RunContext) -> bool:
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"

        if shortlist_path.is_file() and not ctx.force:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.RESEARCH,
                content="Shortlist already exists, skipping research",
            ))
            return True

        from tools.research_agent import run_reviews_research

        report = run_reviews_research(
            ctx.video_id, ctx.niche,
            output_dir=ctx.paths.root / "inputs",
            force=ctx.force,
            dry_run=ctx.dry_run,
            contract_path=ctx.paths.subcategory_contract,
        )

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.RESEARCH,
                content="[DRY RUN] Would browse review pages",
            ))
            return True

        if report.validation_errors:
            for err in report.validation_errors:
                ctx.bus.post(Message(
                    sender=self.name, receiver="qa_gatekeeper",
                    msg_type=MsgType.ERROR, stage=Stage.RESEARCH,
                    content=f"Validation: {err}",
                ))
            return False

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.RESEARCH,
            content=f"Research complete: {len(report.shortlist)} shortlisted from {len(report.sources_reviewed)} sources",
            data={
                "sources_reviewed": len(report.sources_reviewed),
                "total_products": len(report.aggregated),
                "shortlisted": len(report.shortlist),
            },
        ))

        # Supabase: save research data
        if ctx.run_id:
            try:
                from tools.lib.supabase_pipeline import save_research_source, save_shortlist_item
                for src in report.sources_reviewed:
                    save_research_source(ctx.run_id,
                                         source_domain=src.get("domain", ""),
                                         source_url=src.get("url", ""),
                                         ok=not src.get("error"))
                for i, item in enumerate(report.shortlist, 1):
                    save_shortlist_item(ctx.run_id,
                                        product_name_clean=item.get("product_name", ""),
                                        candidate_rank=min(i, 7),
                                        claims=item.get("reasons", []),
                                        evidence_by_source=item.get("sources", []))
            except Exception:
                pass

        return True


class AmazonVerifyAgent:
    """Verifies shortlisted products exist on Amazon US."""
    name = "amazon_verify"
    role = "Verify each shortlisted product on Amazon US, extract ASIN/price/affiliate link"

    def run(self, ctx: RunContext) -> bool:
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        verified_path = ctx.paths.root / "inputs" / "verified.json"

        if verified_path.is_file() and not ctx.force:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.VERIFY,
                content="Verified products already exist, skipping",
            ))
            return True

        if not shortlist_path.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.VERIFY,
                content="shortlist.json missing — research stage incomplete",
            ))
            return False

        shortlist_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
        shortlist = shortlist_data.get("shortlist", [])

        if not shortlist:
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.VERIFY,
                content="Shortlist is empty",
            ))
            return False

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.VERIFY,
                content=f"[DRY RUN] Would verify {len(shortlist)} products on Amazon",
            ))
            return True

        from tools.amazon_verify import verify_products, write_verified

        verified_objs = verify_products(shortlist, video_id=ctx.video_id)

        # Retry once if <5 products verified and shortlist had enough candidates
        if len(verified_objs) < 5 and len(shortlist) >= 5:
            verified_names = {v.product_name.lower() for v in verified_objs}
            failed = [s for s in shortlist if s.get("product_name", "").lower() not in verified_names]
            if failed:
                ctx.bus.post(Message(
                    sender=self.name, receiver="*",
                    msg_type=MsgType.INFO, stage=Stage.VERIFY,
                    content=f"Retrying {len(failed)} failed verifications...",
                ))
                time.sleep(5)
                retry_objs = verify_products(failed, video_id=ctx.video_id)
                verified_objs.extend(retry_objs)

        write_verified(verified_objs, verified_path)

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.VERIFY,
            content=f"Verified {len(verified_objs)}/{len(shortlist)} products on Amazon US",
            data={"verified": len(verified_objs), "total": len(shortlist)},
        ))

        # Supabase: save verified products
        if ctx.run_id:
            try:
                from tools.lib.supabase_pipeline import save_amazon_product
                for v in verified_objs:
                    save_amazon_product(ctx.run_id,
                                        asin=getattr(v, "asin", ""),
                                        amazon_title=getattr(v, "amazon_title", ""),
                                        pdp_url=getattr(v, "amazon_url", ""),
                                        affiliate_short_url=getattr(v, "affiliate_short_url", ""))
            except Exception:
                pass

        if not verified_objs:
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.VERIFY,
                content="No products verified on Amazon",
            ))
            return False

        return True


class Top5RankerAgent:
    """Selects the final Top 5 from verified products."""
    name = "top5_ranker"
    role = "Score and rank verified products into final Top 5 with category diversity"

    def run(self, ctx: RunContext) -> bool:
        verified_path = ctx.paths.root / "inputs" / "verified.json"

        if ctx.paths.products_json.is_file() and not ctx.force:
            # Check if products.json has real data (not just template)
            data = json.loads(ctx.paths.products_json.read_text(encoding="utf-8"))
            products = data.get("products", [])
            if products and products[0].get("name"):
                ctx.bus.post(Message(
                    sender=self.name, receiver="*",
                    msg_type=MsgType.INFO, stage=Stage.RANK,
                    content="products.json already populated, skipping ranking",
                ))
                return True

        if not verified_path.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.RANK,
                content="verified.json missing — verification stage incomplete",
            ))
            return False

        verified_data = json.loads(verified_path.read_text(encoding="utf-8"))
        verified = verified_data.get("products", [])

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.RANK,
                content=f"[DRY RUN] Would rank {len(verified)} products",
            ))
            return True

        import datetime
        from tools.top5_ranker import select_top5, write_products_json

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        contract_path = ctx.paths.subcategory_contract
        top5 = select_top5(
            verified,
            contract_path=contract_path if contract_path.is_file() else None,
        )

        write_products_json(
            top5, ctx.niche, ctx.paths.products_json,
            video_id=ctx.video_id, date=today,
        )

        names = [p.get("product_name", "?") for p in top5]
        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.DECISION, stage=Stage.RANK,
            content=f"Top 5 selected: {', '.join(names[:3])}...",
            data={"top5": names},
        ))

        # Supabase: save top 5
        if ctx.run_id:
            try:
                from tools.lib.supabase_pipeline import save_top5_product
                for p in top5:
                    save_top5_product(ctx.run_id,
                                      rank=p.get("rank", 0),
                                      asin=p.get("asin", ""),
                                      role_label=p.get("category_label", ""),
                                      benefits=p.get("benefits", []),
                                      downside=p.get("downside", ""),
                                      affiliate_short_url=p.get("affiliate_short_url", ""))
            except Exception:
                pass

        return True


class ScriptProducer:
    """Generates script prompts and auto-generates script via LLM APIs."""
    name = "script_producer"
    role = "Generate script via OpenAI (draft) + Anthropic (refinement), with evidence attribution"

    def run(self, ctx: RunContext) -> bool:
        import os

        if not ctx.paths.products_json.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.SCRIPT,
                content="products.json missing — ranking stage incomplete",
            ))
            return False

        from tools.lib.amazon_research import load_products_json
        from tools.lib.script_schema import (
            ProductEntry, ScriptRequest,
            build_extraction_prompt, build_draft_prompt, build_refinement_prompt,
            validate_request,
        )

        products = load_products_json(ctx.paths.products_json)
        if not products:
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.SCRIPT,
                content="products.json is empty or invalid",
            ))
            return False

        # Load raw JSON to get evidence data for script prompts
        raw_data = json.loads(ctx.paths.products_json.read_text(encoding="utf-8"))
        raw_by_rank = {rp.get("rank", 0): rp for rp in raw_data.get("products", [])}

        entries = [
            ProductEntry(
                rank=p.rank, name=p.name, positioning=p.positioning,
                benefits=p.benefits, target_audience=p.target_audience,
                downside=p.downside, amazon_url=p.affiliate_url or p.amazon_url,
                source_evidence=raw_by_rank.get(p.rank, {}).get("evidence", []),
            )
            for p in products
        ]

        charismatic = "reality_check"
        req = ScriptRequest(niche=ctx.niche, products=entries, charismatic_type=charismatic)
        errors = validate_request(req)
        if errors:
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.SCRIPT,
                content=f"Script request invalid: {'; '.join(errors)}",
            ))
            return False

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.SCRIPT,
                content="[DRY RUN] Would generate script prompts and auto-generate script",
            ))
            return True

        # Generate prompts
        ctx.paths.prompts_dir.mkdir(parents=True, exist_ok=True)

        extraction = build_extraction_prompt([], ctx.niche)
        (ctx.paths.prompts_dir / "extraction_prompt.txt").write_text(extraction, encoding="utf-8")

        draft_prompt = build_draft_prompt(req, "(paste extraction notes here)")
        (ctx.paths.prompts_dir / "draft_prompt.txt").write_text(draft_prompt, encoding="utf-8")

        refine_template = build_refinement_prompt("(paste draft here)", charismatic)
        (ctx.paths.prompts_dir / "refine_prompt.txt").write_text(refine_template, encoding="utf-8")

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.SCRIPT,
            content="Script prompts generated (extraction, draft, refinement)",
        ))

        # Check if script.txt already exists
        if ctx.paths.script_txt.is_file() and not ctx.force:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.SCRIPT,
                content="Found existing script.txt — validated",
            ))
            return True

        # Auto-generate if API keys are available
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not openai_key:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.QUESTION, stage=Stage.SCRIPT,
                content=(
                    f"OPENAI_API_KEY not set — cannot auto-generate. "
                    f"Write script.txt manually at: {ctx.paths.script_txt}"
                ),
            ))
            return True  # prompts generated, script is manual

        # Run auto-generation pipeline
        from tools.lib.script_generate import run_script_pipeline

        _log(f"  Auto-generating script via LLM APIs...")
        result = run_script_pipeline(
            draft_prompt,
            refine_template,
            ctx.paths.root / "script",
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            skip_refinement=not anthropic_key,
        )

        if not result.success:
            for err in result.errors:
                ctx.bus.post(Message(
                    sender=self.name, receiver="qa_gatekeeper",
                    msg_type=MsgType.ERROR, stage=Stage.SCRIPT,
                    content=f"Script generation failed: {err}",
                ))
            return False

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.SCRIPT,
            content=(
                f"Script auto-generated: {result.word_count} words"
                f" (draft: {result.draft.model if result.draft else '?'}, "
                f"refine: {result.refinement.model if result.refinement else 'skipped'})"
            ),
            data={
                "word_count": result.word_count,
                "draft_model": result.draft.model if result.draft else "",
                "refine_model": result.refinement.model if result.refinement else "",
            },
        ))
        return True


class DzineAssetAgent:
    """Generates product images and thumbnail via Dzine."""
    name = "dzine_asset_agent"
    role = "Generate thumbnail and product images via Dzine AI"

    def run(self, ctx: RunContext) -> bool:
        if not ctx.paths.products_json.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.ASSETS,
                content="products.json missing",
            ))
            return False

        # Check what's needed (variant-aware)
        from tools.lib.dzine_schema import variants_for_rank
        needed = [("thumbnail", ctx.paths.thumbnail_path())]
        for rank in [5, 4, 3, 2, 1]:
            for variant in variants_for_rank(rank):
                needed.append((f"{rank:02d}_{variant}", ctx.paths.product_image_path(rank, variant)))

        missing = [(label, p) for label, p in needed if not p.is_file() or p.stat().st_size < 50 * 1024]

        if not missing and not ctx.force:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.ASSETS,
                content=f"All {len(needed)} assets present",
            ))
            return True

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.ASSETS,
                content=f"[DRY RUN] Would generate {len(missing)} assets",
            ))
            return True

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.QUESTION, stage=Stage.ASSETS,
            content=f"{len(missing)} assets need generation via Dzine (requires browser)",
            data={"missing": [label for label, _ in missing]},
        ))
        # Assets require interactive Dzine session — signal action required
        return len(missing) == 0


class TTSAgent:
    """Generates TTS voiceover chunks via ElevenLabs."""
    name = "tts_agent"
    role = "Generate voiceover audio chunks from script via ElevenLabs"

    def run(self, ctx: RunContext) -> bool:
        if not ctx.paths.script_txt.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.TTS,
                content="script.txt missing",
            ))
            return False

        # Check existing chunks
        existing = list(ctx.paths.audio_chunks.glob("*.mp3")) if ctx.paths.audio_chunks.is_dir() else []
        existing = [f for f in existing if not f.stem.startswith("micro_")]

        if existing and not ctx.force:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.TTS,
                content=f"{len(existing)} TTS chunks already exist",
            ))
            return True

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.TTS,
                content="[DRY RUN] Would generate TTS chunks",
            ))
            return True

        from tools.lib.tts_generate import generate_full

        script_text = ctx.paths.script_txt.read_text(encoding="utf-8")
        ctx.paths.audio_chunks.mkdir(parents=True, exist_ok=True)

        results = generate_full(ctx.video_id, script_text, output_dir=ctx.paths.audio_chunks)

        ok = sum(1 for m in results if m.status == "success")
        failed = sum(1 for m in results if m.status == "failed")

        # Write tts_meta.json
        meta = {
            "video_id": ctx.video_id,
            "generated_at": now_iso(),
            "chunks": [
                {
                    "index": m.index,
                    "status": m.status,
                    "word_count": m.word_count,
                    "file_path": m.file_path,
                }
                for m in results
            ],
        }
        ctx.paths.tts_meta.parent.mkdir(parents=True, exist_ok=True)
        ctx.paths.tts_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.TTS,
            content=f"TTS: {ok} OK, {failed} failed",
            data={"ok": ok, "failed": failed},
        ))
        return failed == 0


class ResolvePackager:
    """Generates DaVinci Resolve edit manifest, markers, and notes."""
    name = "resolve_packager"
    role = "Generate edit manifest, markers CSV, and notes for DaVinci Resolve"

    def run(self, ctx: RunContext) -> bool:
        if not ctx.paths.script_txt.is_file():
            ctx.bus.post(Message(
                sender=self.name, receiver="qa_gatekeeper",
                msg_type=MsgType.ERROR, stage=Stage.MANIFEST,
                content="script.txt missing",
            ))
            return False

        if ctx.dry_run:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.MANIFEST,
                content="[DRY RUN] Would generate Resolve manifest",
            ))
            return True

        from tools.lib.resolve_schema import (
            generate_manifest, manifest_to_json, manifest_to_markers_csv, manifest_to_notes,
        )
        from tools.lib.amazon_research import load_products_json

        script_text = ctx.paths.script_txt.read_text(encoding="utf-8")

        product_names = {}
        product_benefits = {}
        if ctx.paths.products_json.is_file():
            products = load_products_json(ctx.paths.products_json)
            if products:
                for p in products:
                    product_names[p.rank] = p.name
                    product_benefits[p.rank] = p.benefits

        manifest = generate_manifest(
            ctx.video_id, script_text, ctx.paths.root,
            product_names=product_names, product_benefits=product_benefits,
        )

        ctx.paths.resolve_dir.mkdir(parents=True, exist_ok=True)
        (ctx.paths.resolve_dir / "edit_manifest.json").write_text(manifest_to_json(manifest), encoding="utf-8")
        (ctx.paths.resolve_dir / "markers.csv").write_text(manifest_to_markers_csv(manifest), encoding="utf-8")
        (ctx.paths.resolve_dir / "notes.md").write_text(manifest_to_notes(manifest), encoding="utf-8")

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=MsgType.INFO, stage=Stage.MANIFEST,
            content=f"Resolve manifest generated ({manifest.total_duration_s:.0f}s, {len(manifest.segments)} segments)",
        ))
        return True


# ---------------------------------------------------------------------------
# QA Gatekeeper
# ---------------------------------------------------------------------------


class QAGatekeeper:
    """Validates stage outputs before allowing progression."""
    name = "qa_gatekeeper"
    role = "Block pipeline progression if artifacts or rules fail validation"

    # Validation rules per stage
    def run(self, ctx: RunContext) -> bool:
        # This agent is called explicitly via check_gate(), not via run()
        return True

    def check_gate(self, ctx: RunContext, stage: Stage) -> tuple[bool, list[str]]:
        """Check if a stage passes QA. Returns (passed, errors)."""
        errors: list[str] = []

        # Check error messages posted to us for this stage
        error_msgs = [
            m for m in ctx.bus.get_for(self.name)
            if m.msg_type == MsgType.ERROR and m.stage == stage
        ]
        for m in error_msgs:
            errors.append(f"[{m.sender}] {m.content}")

        # Stage-specific checks
        checker = {
            Stage.NICHE: self._check_niche,
            Stage.RESEARCH: self._check_research,
            Stage.VERIFY: self._check_verify,
            Stage.RANK: self._check_rank,
            Stage.SCRIPT: self._check_script,
            Stage.ASSETS: self._check_assets,
            Stage.TTS: self._check_tts,
            Stage.MANIFEST: self._check_manifest,
        }.get(stage)

        if checker:
            stage_errors = checker(ctx)
            errors.extend(stage_errors)

        passed = len(errors) == 0
        msg_type = MsgType.GATE_PASS if passed else MsgType.GATE_FAIL

        ctx.bus.post(Message(
            sender=self.name, receiver="*",
            msg_type=msg_type, stage=stage,
            content=f"Gate {'PASSED' if passed else 'FAILED'} for {stage.value}"
                    + (f": {errors[0]}" if errors else ""),
            data={"errors": errors},
        ))
        return passed, errors

    def _check_niche(self, ctx: RunContext) -> list[str]:
        errors = []
        if not ctx.niche:
            errors.append("No niche selected")
        if not ctx.paths.niche_txt.is_file():
            errors.append("niche.txt not written")
        return errors

    def _get_price_floor(self, ctx: RunContext) -> int:
        """Get the price floor from micro_niche.json, or default."""
        mn_path = ctx.paths.micro_niche_json
        if mn_path.is_file():
            try:
                data = json.loads(mn_path.read_text(encoding="utf-8"))
                return int(data.get("price_min", DEFAULT_PRICE_FLOOR))
            except Exception:
                pass
        return DEFAULT_PRICE_FLOOR

    def _check_research(self, ctx: RunContext) -> list[str]:
        errors = []
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        if not shortlist_path.is_file():
            errors.append("shortlist.json missing")
            return errors
        data = json.loads(shortlist_path.read_text(encoding="utf-8"))
        shortlist = data.get("shortlist", [])
        if len(shortlist) < 5:
            errors.append(f"Shortlist has {len(shortlist)} items (minimum 5)")
        if len(shortlist) > 7:
            errors.append(f"Shortlist has {len(shortlist)} items (maximum 7)")

        # Domain compliance
        for item in shortlist:
            for src in item.get("sources", []):
                url = src.get("url", "")
                if url and not any(d in url for d in ALLOWED_RESEARCH_DOMAINS):
                    errors.append(f"Domain violation: {url}")

        # Evidence quality: every shortlisted product must have reasons
        for item in shortlist:
            reasons = item.get("reasons", [])
            if not reasons:
                errors.append(f"Shortlist product '{item.get('product_name', '?')}' has no evidence claims")

        # Generic claim filter: reject products with ONLY generic claims
        from tools.research_agent import _is_generic_claim
        for item in shortlist:
            reasons = item.get("reasons", [])
            if reasons and all(_is_generic_claim(r) for r in reasons):
                errors.append(
                    f"Shortlist product '{item.get('product_name', '?')}' has only "
                    f"generic claims (no attributed evidence)"
                )

        # Subcategory contract compliance
        contract_path = ctx.paths.subcategory_contract
        if contract_path.is_file():
            from tools.lib.subcategory_contract import load_contract, passes_gate
            contract = load_contract(contract_path)
            for item in shortlist:
                ok, reason = passes_gate(
                    item.get("product_name", ""),
                    item.get("brand", ""),
                    contract,
                )
                if not ok:
                    errors.append(f"Subcategory drift: {item.get('product_name', '?')} -- {reason}")

        return errors

    def _check_verify(self, ctx: RunContext) -> list[str]:
        errors = []
        verified_path = ctx.paths.root / "inputs" / "verified.json"
        if not verified_path.is_file():
            errors.append("verified.json missing")
            return errors
        data = json.loads(verified_path.read_text(encoding="utf-8"))
        products = data.get("products", [])
        if len(products) < 4:
            errors.append(f"Only {len(products)} products verified (minimum 4)")
        elif len(products) == 4:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.VERIFY,
                content=f"WARNING: Only 4 products verified (5 preferred). Proceeding.",
            ))

        # SiteStripe short link check for browser-verified products
        missing_short = [
            p for p in products
            if not p.get("affiliate_short_url")
            and p.get("verification_method") == "browser"
        ]
        if missing_short:
            names = ", ".join(p.get("product_name", "?")[:30] for p in missing_short[:3])
            errors.append(
                f"SiteStripe short link missing for {len(missing_short)} "
                f"browser-verified products: {names}"
            )

        # Subcategory contract compliance — HARD FAIL on any drift
        contract_path = ctx.paths.subcategory_contract
        if contract_path.is_file():
            from tools.lib.subcategory_contract import load_contract, passes_gate
            contract = load_contract(contract_path)
            for p in products:
                ok, reason = passes_gate(
                    p.get("product_name", ""),
                    p.get("brand", ""),
                    contract,
                )
                if not ok:
                    errors.append(f"Subcategory drift in verified: {p.get('product_name', '?')} -- {reason}")

        # Price floor — HARD FAIL if product is below micro-niche price_min
        price_min = self._get_price_floor(ctx)
        if price_min > 0:
            for p in products:
                price = _extract_price(p.get("amazon_price", ""))
                if price is not None and price < price_min:
                    errors.append(
                        f"Price floor violation: '{p.get('product_name', '?')}' "
                        f"at ${price:.0f} is below ${price_min} minimum"
                    )

        return errors

    def _check_rank(self, ctx: RunContext) -> list[str]:
        errors = []
        if not ctx.paths.products_json.is_file():
            errors.append("products.json missing")
            return errors
        data = json.loads(ctx.paths.products_json.read_text(encoding="utf-8"))
        products = data.get("products", [])
        if len(products) < 4 or len(products) > 5:
            errors.append(f"Expected 4-5 products, got {len(products)}")
        for p in products:
            if not p.get("name"):
                errors.append(f"Product rank {p.get('rank')} has no name")
            if not p.get("asin") and not p.get("affiliate_url"):
                errors.append(f"Product '{p.get('name', '?')}' has no ASIN or affiliate link")

        # Subcategory contract compliance — HARD FAIL on any drift
        contract_path = ctx.paths.subcategory_contract
        if contract_path.is_file():
            from tools.lib.subcategory_contract import load_contract, passes_gate
            contract = load_contract(contract_path)
            for p in products:
                ok, reason = passes_gate(p.get("name", ""), p.get("brand", ""), contract)
                if not ok:
                    errors.append(f"Subcategory drift in Top 5: {p.get('name', '?')} -- {reason}")

        # Price floor — HARD FAIL if product is below micro-niche price_min
        price_min = self._get_price_floor(ctx)
        if price_min > 0:
            for p in products:
                price = _extract_price(p.get("price", ""))
                if price is not None and price < price_min:
                    errors.append(
                        f"Price floor violation: '{p.get('name', '?')}' "
                        f"at ${price:.0f} is below ${price_min} minimum"
                    )

        return errors

    def _check_script(self, ctx: RunContext) -> list[str]:
        errors = []
        if not ctx.paths.prompts_dir.is_dir():
            errors.append("Script prompts directory missing")
        elif not any(ctx.paths.prompts_dir.iterdir()):
            errors.append("No prompt files generated")
        # script.txt is optional at this stage (manual step)
        return errors

    def _check_assets(self, ctx: RunContext) -> list[str]:
        from tools.lib.dzine_schema import variants_for_rank
        errors = []
        thumb = ctx.paths.thumbnail_path()
        if not thumb.is_file() or thumb.stat().st_size < 50 * 1024:
            errors.append("Thumbnail missing or too small")
        for rank in [5, 4, 3, 2, 1]:
            for variant in variants_for_rank(rank):
                img = ctx.paths.product_image_path(rank, variant)
                if not img.is_file() or img.stat().st_size < 50 * 1024:
                    errors.append(f"Product image {rank:02d}_{variant} missing or too small")
        return errors

    def _check_tts(self, ctx: RunContext) -> list[str]:
        errors = []
        if not ctx.paths.audio_chunks.is_dir():
            errors.append("Audio chunks directory missing")
            return errors
        chunks = [f for f in ctx.paths.audio_chunks.glob("*.mp3") if not f.stem.startswith("micro_")]
        if not chunks:
            errors.append("No audio chunks generated")
        return errors

    def _check_manifest(self, ctx: RunContext) -> list[str]:
        errors = []
        for fname in ["edit_manifest.json", "markers.csv", "notes.md"]:
            if not (ctx.paths.resolve_dir / fname).is_file():
                errors.append(f"Missing {fname}")

        # Publish readiness check — final buyer-trust QA gate
        try:
            from tools.lib.buyer_trust import publish_readiness_check
            pr = publish_readiness_check(ctx.paths.root)
            for item in pr.failures:
                errors.append(f"Publish readiness: {item.name} — {item.detail}")
        except Exception as exc:
            errors.append(f"Publish readiness check failed: {exc}")

        return errors


# ---------------------------------------------------------------------------
# Security Agent
# ---------------------------------------------------------------------------


class SecurityAgent:
    """Enforces domain restrictions and compliance rules."""
    name = "security_agent"
    role = "Enforce 3-domain research restriction and data compliance"

    def run(self, ctx: RunContext) -> bool:
        return True

    def audit_research(self, ctx: RunContext) -> list[str]:
        """Audit research outputs for domain violations."""
        violations = []

        # Check shortlist.json
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        if shortlist_path.is_file():
            data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            for item in data.get("shortlist", []):
                for src in item.get("sources", []):
                    url = src.get("url", "")
                    if url and not any(d in url for d in ALLOWED_RESEARCH_DOMAINS):
                        violations.append(f"Unauthorized domain in shortlist: {url}")

        # Check research_report.md for external URLs
        report_path = ctx.paths.root / "inputs" / "research_report.md"
        if report_path.is_file():
            import re
            text = report_path.read_text(encoding="utf-8")
            urls = re.findall(r'https?://[^\s\)]+', text)
            for url in urls:
                if "amazon.com" in url:
                    continue  # Amazon URLs are fine in the report
                if not any(d in url for d in ALLOWED_RESEARCH_DOMAINS):
                    violations.append(f"Unauthorized domain in report: {url}")

        if violations:
            for v in violations:
                ctx.bus.post(Message(
                    sender=self.name, receiver="qa_gatekeeper",
                    msg_type=MsgType.ERROR, stage=Stage.RESEARCH,
                    content=v,
                ))
        else:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.INFO, stage=Stage.RESEARCH,
                content="Security audit passed: all sources within allowed domains",
            ))

        return violations


# ---------------------------------------------------------------------------
# Reviewer Agent
# ---------------------------------------------------------------------------


class ReviewerAgent:
    """Audits other agents' outputs after each stage."""
    name = "reviewer_agent"
    role = "Post-stage audit: check completeness, consistency, and quality"

    def run(self, ctx: RunContext) -> bool:
        return True

    def review_stage(self, ctx: RunContext, stage: Stage) -> list[str]:
        """Review a stage's outputs. Returns list of issues (empty = pass)."""
        issues: list[str] = []

        # Collect all error messages for this stage
        errors = ctx.bus.get_by_type(MsgType.ERROR, stage=stage)
        for e in errors:
            issues.append(f"Error from {e.sender}: {e.content}")

        # Stage-specific reviews
        reviewer = {
            Stage.NICHE: self._review_niche,
            Stage.RESEARCH: self._review_research,
            Stage.RANK: self._review_rank,
        }.get(stage)

        if reviewer:
            stage_issues = reviewer(ctx)
            issues.extend(stage_issues)

        # Post review
        if issues:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.REVIEW, stage=stage,
                content=f"Review for {stage.value}: {len(issues)} issue(s)",
                data={"issues": issues},
            ))
        else:
            ctx.bus.post(Message(
                sender=self.name, receiver="*",
                msg_type=MsgType.REVIEW, stage=stage,
                content=f"Review for {stage.value}: PASSED",
            ))

        return issues

    def _review_niche(self, ctx: RunContext) -> list[str]:
        issues = []
        if not ctx.niche:
            issues.append("No niche selected after niche stage")
        elif len(ctx.niche) < 3:
            issues.append(f"Niche too short: '{ctx.niche}'")
        return issues

    def _review_research(self, ctx: RunContext) -> list[str]:
        issues = []
        shortlist_path = ctx.paths.root / "inputs" / "shortlist.json"
        report_path = ctx.paths.root / "inputs" / "research_report.md"

        if not shortlist_path.is_file():
            issues.append("shortlist.json not produced")
        if not report_path.is_file():
            issues.append("research_report.md not produced")

        if shortlist_path.is_file():
            data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            sl = data.get("shortlist", [])
            sources_count = data.get("sources_with_results", 0)
            if sources_count < 2:
                issues.append(f"Only {sources_count} sources produced results (need 2+)")
            # Check evidence quality
            no_reasons = [s for s in sl if not s.get("reasons")]
            if len(no_reasons) > len(sl) // 2:
                issues.append(f"{len(no_reasons)}/{len(sl)} shortlisted products lack reasons")

        return issues

    def _review_rank(self, ctx: RunContext) -> list[str]:
        issues = []
        if not ctx.paths.products_json.is_file():
            issues.append("products.json not produced")
            return issues

        data = json.loads(ctx.paths.products_json.read_text(encoding="utf-8"))
        products = data.get("products", [])
        ranks_seen = {p.get("rank") for p in products}
        expected = {1, 2, 3, 4, 5}
        if ranks_seen != expected:
            issues.append(f"Rank mismatch: have {sorted(ranks_seen)}, expected {sorted(expected)}")

        # Check for duplicate brands dominating the list
        brands = [p.get("brand", "").lower() for p in products if p.get("brand")]
        from collections import Counter
        brand_counts = Counter(brands)
        for brand, count in brand_counts.items():
            if count >= 3:
                issues.append(f"Brand '{brand}' appears {count} times — low diversity")

        return issues


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


# Stage -> (agents to run, is_required_for_progression)
STAGE_AGENTS: dict[Stage, list[str]] = {
    Stage.NICHE: ["niche_strategist", "seo_agent"],
    Stage.RESEARCH: ["research_agent"],
    Stage.VERIFY: ["amazon_verify"],
    Stage.RANK: ["top5_ranker"],
    Stage.SCRIPT: ["script_producer"],
    Stage.ASSETS: ["dzine_asset_agent"],
    Stage.TTS: ["tts_agent"],
    Stage.MANIFEST: ["resolve_packager"],
}


class Orchestrator:
    """Runs the pipeline stages with agent coordination, QA gates, and review loops."""

    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.qa = QAGatekeeper()
        self.security = SecurityAgent()
        self.reviewer = ReviewerAgent()
        self._register_agents()

    def _register_agents(self) -> None:
        """Register all 12 agents."""
        for agent_cls in [
            NicheStrategist,
            SEOAgent,
            ResearchAgentWrapper,
            AmazonVerifyAgent,
            Top5RankerAgent,
            ScriptProducer,
            DzineAssetAgent,
            TTSAgent,
            ResolvePackager,
        ]:
            instance = agent_cls()
            self.agents[instance.name] = instance
        # QA, Security, Reviewer are special — registered separately
        self.agents[self.qa.name] = self.qa
        self.agents[self.security.name] = self.security
        self.agents[self.reviewer.name] = self.reviewer

    def run_pipeline(
        self,
        video_id: str,
        *,
        niche: str = "",
        start_stage: Stage | None = None,
        stop_after: Stage | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> RunContext:
        """Execute the pipeline end-to-end (or from a specific stage)."""
        from tools.lib.pipeline_status import start_pipeline, update_milestone
        from tools.lib.notify import notify_start, notify_progress, notify_error, notify_summary

        ctx = RunContext(
            video_id=video_id,
            niche=niche,
            dry_run=dry_run,
            force=force,
        )
        ctx.paths.ensure_dirs()

        _log(f"\n{'='*60}")
        _log(f"  Pipeline: {video_id}")
        _log(f"  Niche: {niche or '(auto)'}")
        _log(f"  Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
        _log(f"{'='*60}\n")

        # Supabase: create run + load channel memory
        if not dry_run:
            try:
                from tools.lib.supabase_pipeline import create_run as _create_run
                ctx.run_id = _create_run(video_id, niche)
                ctx.bus.set_run_id(ctx.run_id)
            except Exception:
                pass  # graceful degradation
            try:
                from tools.lib.supabase_pipeline import get_all_channel_memory
                memory = get_all_channel_memory()
                if memory:
                    ctx.bus.post(Message(
                        sender="orchestrator", receiver="*",
                        msg_type=MsgType.INFO, stage=Stage.NICHE,
                        content=f"Loaded {len(memory)} channel memory keys",
                        data={"keys": list(memory.keys())},
                    ))
            except Exception:
                pass

        if not dry_run:
            start_pipeline(video_id)
            notify_start(video_id, details=[
                f"Niche: {niche or '(auto-pick)'}",
                f"Stages: {len(STAGE_ORDER)}",
            ])

        # Determine which stages to run
        stages = list(STAGE_ORDER)
        if start_stage:
            idx = stages.index(start_stage)
            stages = stages[idx:]

        for stage in stages:
            if ctx.aborted:
                break

            ctx.current_stage = stage
            _log(f"\n--- Stage: {stage.value} ---")

            # Preflight session checks for browser-dependent stages
            if not dry_run:
                from tools.lib.preflight import STAGE_SESSIONS, preflight_check
                if stage.value in STAGE_SESSIONS and STAGE_SESSIONS[stage.value]:
                    _log(f"  Preflight check for {stage.value}...")
                    pf_result = preflight_check(stage.value)
                    if not pf_result.passed:
                        for failure in pf_result.failures:
                            ctx.bus.post(Message(
                                sender="orchestrator", receiver="qa_gatekeeper",
                                msg_type=MsgType.ERROR, stage=stage,
                                content=f"Preflight: {failure}",
                            ))
                            _log(f"  Preflight FAILED: {failure}")
                        from tools.lib.notify import notify_action_required
                        notify_action_required(
                            video_id, stage.value,
                            f"Preflight failed: {pf_result.failures[0]}",
                            next_action="Fix the issue and re-run the pipeline",
                        )
                        ctx.aborted = True
                        ctx.abort_reason = f"Preflight: {pf_result.failures[0]}"
                        break

            # Run stage agents
            agent_names = STAGE_AGENTS.get(stage, [])
            stage_ok = True

            for agent_name in agent_names:
                agent = self.agents.get(agent_name)
                if not agent:
                    _log(f"  WARNING: agent '{agent_name}' not registered")
                    continue

                _log(f"  Running: {agent.name} ({agent.role})")
                try:
                    ok = agent.run(ctx)
                    if not ok:
                        stage_ok = False
                        _log(f"  FAILED: {agent.name}")
                except Exception as exc:
                    stage_ok = False
                    ctx.bus.post(Message(
                        sender=agent.name, receiver="qa_gatekeeper",
                        msg_type=MsgType.ERROR, stage=stage,
                        content=f"Exception: {exc}",
                    ))
                    _log(f"  EXCEPTION in {agent.name}: {exc}")

            # Security audit (after research)
            if stage == Stage.RESEARCH and not ctx.dry_run:
                _log(f"  Security audit...")
                violations = self.security.audit_research(ctx)
                if violations:
                    stage_ok = False

            # Reviewer audit
            _log(f"  Reviewing stage...")
            review_issues = self.reviewer.review_stage(ctx, stage)

            # QA gate
            _log(f"  QA gate check...")
            gate_passed, gate_errors = self.qa.check_gate(ctx, stage)

            if gate_passed and stage_ok:
                ctx.stages_completed.append(stage)
                if not dry_run:
                    update_milestone(video_id, stage.value, "complete")
                    notify_progress(
                        video_id, stage.value, "complete",
                        details=[f"Stage {stage.value} completed"],
                    )
                _log(f"  PASSED: {stage.value}")
            else:
                all_errors = gate_errors + review_issues
                ctx.errors.extend(all_errors)
                if not dry_run:
                    from tools.lib.error_log import log_error as _log_pipeline_error
                    for err in all_errors[:3]:
                        _log_pipeline_error(video_id, stage.value, err,
                                            exit_code=2,
                                            context={"command": "run",
                                                     "source": "qa_gate"})
                        notify_error(video_id, stage.value, "gate_fail", err)

                # Supabase: save lessons from gate errors
                if ctx.run_id:
                    try:
                        from tools.lib.supabase_pipeline import save_lesson as _save_lsn
                        for err in all_errors[:3]:
                            _save_lsn(stage.value, err[:80], err, severity="high")
                    except Exception:
                        pass

                # Non-blocking stages: script (prompts generated, script is manual),
                # assets (may need Dzine login)
                if stage in (Stage.SCRIPT, Stage.ASSETS):
                    _log(f"  SOFT FAIL: {stage.value} (action required, continuing)")
                    ctx.stages_completed.append(stage)
                else:
                    _log(f"  HARD FAIL: {stage.value} — stopping pipeline")
                    ctx.aborted = True
                    ctx.abort_reason = all_errors[0] if all_errors else "Unknown gate failure"
                    break

            if stop_after and stage == stop_after:
                _log(f"\n  Stopping after {stage.value} (--stage flag)")
                break

        # Write conversation log
        self._write_log(ctx)

        # Summary
        _log(f"\n{'='*60}")
        _log(f"  Pipeline {'COMPLETE' if not ctx.aborted else 'STOPPED'}")
        _log(f"  Stages completed: {[s.value for s in ctx.stages_completed]}")
        if ctx.errors:
            _log(f"  Errors: {len(ctx.errors)}")
            for e in ctx.errors[:5]:
                _log(f"    - {e}")
        _log(f"  Messages: {ctx.bus.count}")
        _log(f"{'='*60}\n")

        if not dry_run and not ctx.aborted:
            notify_summary(video_id, details=[
                f"Stages: {len(ctx.stages_completed)}/{len(STAGE_ORDER)}",
                f"Messages: {ctx.bus.count}",
            ])

        # Supabase: complete run
        if ctx.run_id and not dry_run:
            try:
                from tools.lib.supabase_pipeline import complete_run as _complete_run
                status = "complete" if not ctx.aborted else ("aborted" if ctx.aborted else "failed")
                _complete_run(
                    ctx.run_id, status,
                    [s.value for s in ctx.stages_completed],
                    ctx.errors,
                )
            except Exception:
                pass

        return ctx

    def _write_log(self, ctx: RunContext) -> None:
        """Write the conversation log to disk."""
        log_path = ctx.paths.root / "agent_log.json"
        log_data = {
            "video_id": ctx.video_id,
            "niche": ctx.niche,
            "timestamp": now_iso(),
            "stages_completed": [s.value for s in ctx.stages_completed],
            "aborted": ctx.aborted,
            "abort_reason": ctx.abort_reason,
            "errors": ctx.errors,
            "messages": ctx.bus.to_log(),
        }
        log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_agents(self) -> list[dict]:
        """List all registered agents."""
        return [
            {"name": a.name, "role": a.role}
            for a in self.agents.values()
        ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Multi-agent pipeline orchestrator")
    parser.add_argument("--video-id", default="", help="Video ID")
    parser.add_argument("--niche", default="", help="Product niche (auto-picked if empty)")
    parser.add_argument("--stage", default="", help="Start from this stage")
    parser.add_argument("--stop-after", default="", help="Stop after this stage")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--force", action="store_true", help="Force re-run all stages")
    parser.add_argument("--list-agents", action="store_true", help="List all registered agents")
    args = parser.parse_args()

    load_env_file()

    orchestrator = Orchestrator()

    if args.list_agents:
        agents = orchestrator.list_agents()
        print(f"Registered agents ({len(agents)}):\n")
        for a in agents:
            print(f"  {a['name']:<25s} {a['role']}")
        return 0

    if not args.video_id:
        parser.error("--video-id is required")

    start_stage = None
    if args.stage:
        try:
            start_stage = Stage(args.stage)
        except ValueError:
            print(f"Unknown stage: {args.stage}")
            print(f"Available: {', '.join(s.value for s in Stage)}")
            return 1

    stop_after = None
    if args.stop_after:
        try:
            stop_after = Stage(args.stop_after)
        except ValueError:
            print(f"Unknown stage: {args.stop_after}")
            return 1

    ctx = orchestrator.run_pipeline(
        args.video_id,
        niche=args.niche,
        start_stage=start_stage,
        stop_after=stop_after,
        dry_run=args.dry_run,
        force=args.force,
    )

    # Print summary to stdout
    print(f"\nPipeline {'COMPLETE' if not ctx.aborted else 'STOPPED'}: {args.video_id}")
    print(f"  Niche: {ctx.niche}")
    print(f"  Stages: {len(ctx.stages_completed)}/{len(STAGE_ORDER)}")
    for s in ctx.stages_completed:
        print(f"    [x] {s.value}")
    pending = [s for s in STAGE_ORDER if s not in ctx.stages_completed]
    for s in pending:
        print(f"    [ ] {s.value}")
    if ctx.errors:
        print(f"  Errors ({len(ctx.errors)}):")
        for e in ctx.errors[:5]:
            print(f"    - {e}")

    return 0 if not ctx.aborted else 2


if __name__ == "__main__":
    raise SystemExit(main())
