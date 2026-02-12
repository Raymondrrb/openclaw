import type {
  PipelineRun,
  Script,
  Top5Product,
  ShortlistItem,
  AmazonProduct,
  ResearchSource,
  Niche,
} from "@/lib/types";

export type Priority = "critical" | "normal" | "info";

export interface NextAction {
  action: string;
  command: string;
  priority: Priority;
}

export interface ConstraintWarning {
  check: string;
  message: string;
}

const STAGES = ["niche", "research", "verify", "rank", "script", "assets", "tts", "manifest"];
const ALLOWED_DOMAINS = ["nytimes.com", "rtings.com", "pcmag.com"];

export function computeNextAction(
  run: PipelineRun | null,
  script: Script | null
): NextAction {
  if (!run) {
    return {
      action: "No active pipeline. Start a new video.",
      command: "python3 tools/pipeline.py day",
      priority: "normal",
    };
  }

  const vid = run.video_id;
  const done = new Set(run.stages_completed ?? []);

  if (run.status === "failed") {
    const failedStage = STAGES.find((s) => !done.has(s)) ?? "niche";
    return {
      action: `Pipeline failed: ${run.error_message || "unknown error"}. Fix the issue and re-run.`,
      command: `python3 tools/pipeline.py run --video-id ${vid} --stage ${failedStage}`,
      priority: "critical",
    };
  }

  if (run.status === "aborted") {
    return {
      action: `Pipeline aborted: ${run.error_message || "review needed"}. Review and restart.`,
      command: `python3 tools/pipeline.py run --video-id ${vid}`,
      priority: "critical",
    };
  }

  if (!done.has("niche")) {
    return {
      action: "Initialize a new video with niche selection.",
      command: `python3 tools/pipeline.py init --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("research")) {
    return {
      action: "Run research stage.",
      command: `python3 tools/pipeline.py research --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("verify")) {
    return {
      action: "Run Amazon verification.",
      command: `python3 tools/pipeline.py research --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("rank")) {
    return {
      action: "Run Top 5 ranking.",
      command: `python3 tools/pipeline.py research --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("script")) {
    if (!script || script.status === "draft" || script.status === "brief") {
      return {
        action: "Run script generation.",
        command: `python3 tools/pipeline.py script --video-id ${vid}`,
        priority: "normal",
      };
    }
    if (script.status === "raw" || script.status === "reviewed") {
      return {
        action: "Review generated script and approve.",
        command: `(manual) Review script.txt in artifacts/videos/${vid}/script/`,
        priority: "critical",
      };
    }
  }

  if (!done.has("assets")) {
    return {
      action: "Generate Dzine assets.",
      command: `python3 tools/pipeline.py assets --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("tts")) {
    return {
      action: "Generate TTS voiceover.",
      command: `python3 tools/pipeline.py tts --video-id ${vid}`,
      priority: "normal",
    };
  }

  if (!done.has("manifest")) {
    return {
      action: "Generate DaVinci Resolve manifest.",
      command: `python3 tools/pipeline.py manifest --video-id ${vid}`,
      priority: "normal",
    };
  }

  return {
    action: "All stages complete! Open DaVinci Resolve and edit the video.",
    command: "",
    priority: "info",
  };
}

export function computeWarnings(opts: {
  shortlist: ShortlistItem[];
  amazonProducts: AmazonProduct[];
  top5: Top5Product[];
  sources: ResearchSource[];
  script: Script | null;
  niche: Niche | null;
}): ConstraintWarning[] {
  const warnings: ConstraintWarning[] = [];

  if (opts.shortlist.length > 7) {
    warnings.push({
      check: "shortlist_overflow",
      message: `Shortlist has ${opts.shortlist.length} items (max 7)`,
    });
  }

  const verified = opts.amazonProducts.filter((p) => !p.rejected);
  if (verified.length > 0 && verified.length < 4) {
    warnings.push({
      check: "too_few_verified",
      message: `Only ${verified.length} verified products (need 4)`,
    });
  }

  for (const p of opts.top5) {
    if (!p.affiliate_short_url) {
      warnings.push({
        check: "missing_affiliate",
        message: `Product rank ${p.rank} missing affiliate link`,
      });
    }
  }

  if (opts.niche) {
    for (const p of opts.top5) {
      if (p.price !== null && p.price < opts.niche.price_min) {
        warnings.push({
          check: "price_floor",
          message: `Product rank ${p.rank} at $${p.price} below floor $${opts.niche.price_min}`,
        });
      }
    }
  }

  for (const s of opts.sources) {
    if (s.source_domain && !ALLOWED_DOMAINS.includes(s.source_domain)) {
      warnings.push({
        check: "domain_violation",
        message: `Source ${s.source_domain} not in allowed list`,
      });
    }
  }

  if (
    opts.script &&
    !opts.script.has_disclosure &&
    ["reviewed", "final", "approved"].includes(opts.script.status)
  ) {
    warnings.push({
      check: "missing_disclosure",
      message: "Script missing FTC affiliate disclosure",
    });
  }

  return warnings;
}
