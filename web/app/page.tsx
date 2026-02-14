import {
  getLatestRun,
  getNiche,
  getTop5Products,
  getShortlistItems,
  getAmazonProducts,
  getResearchSources,
  getScript,
  getGateEvents,
} from "@/lib/queries";
import { computeNextAction, computeWarnings } from "@/lib/next-action";
import { NextActionCard } from "@/components/next-action-card";
import { StagePipeline } from "@/components/stage-pipeline";
import { ProductCard } from "@/components/product-card";
import { IssueList } from "@/components/issue-list";

const statusBadge: Record<string, string> = {
  running: "bg-yellow-900/40 text-[var(--yellow)]",
  complete: "bg-green-900/40 text-[var(--green)]",
  failed: "bg-red-900/40 text-[var(--red)]",
  aborted: "bg-red-900/40 text-[var(--red)]",
};

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const run = await getLatestRun();

  if (!run) {
    const action = computeNextAction(null, null);
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Rayviews Lab Ops</h1>
        <p className="text-sm text-[var(--muted)]">No pipeline runs yet.</p>
        <NextActionCard action={action} />
      </div>
    );
  }

  const [niche, top5, shortlist, amazonProducts, sources, script, gateEvents] =
    await Promise.all([
      getNiche(run.id),
      getTop5Products(run.id),
      getShortlistItems(run.id),
      getAmazonProducts(run.id),
      getResearchSources(run.id),
      getScript(run.id),
      getGateEvents(run.id),
    ]);

  const nextAction = computeNextAction(run, script);
  const warnings = computeWarnings({
    shortlist,
    amazonProducts,
    top5,
    sources,
    script,
    niche,
  });
  const gateFailures = gateEvents.filter((e) => e.event_type === "gate_fail");
  const subcategory =
    niche?.subcategory || (run.micro_niche as Record<string, string>)?.subcategory || "";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Rayviews Lab Ops</h1>
        <span className="text-xs text-[var(--muted)]">
          Updated {new Date().toLocaleString()}
        </span>
      </div>

      {/* Today's Video */}
      <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">{run.video_id}</h2>
            <p className="text-sm text-[var(--muted)]">
              {run.cluster}
              {subcategory ? ` / ${subcategory}` : ""}
            </p>
            {niche && niche.price_min > 0 && (
              <p className="text-xs text-[var(--muted)]">
                Price band: ${niche.price_min} - ${niche.price_max}
              </p>
            )}
          </div>
          <div className="text-right">
            <span
              className={`inline-block rounded px-2 py-1 text-xs font-medium ${statusBadge[run.status] ?? ""}`}
            >
              {run.status}
            </span>
            <p className="mt-1 text-xs text-[var(--muted)]">
              {new Date(run.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </div>

      {/* Next Action */}
      <NextActionCard action={nextAction} />

      {/* Pipeline Stages */}
      <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
        <h3 className="mb-3 text-sm font-bold text-[var(--muted)]">Pipeline Stages</h3>
        <StagePipeline
          stagesCompleted={run.stages_completed}
          currentStatus={run.status}
          gateEvents={gateEvents}
        />
      </div>

      {/* Top 5 Products */}
      {top5.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-bold text-[var(--muted)]">Top 5 Products</h3>
          <div className="space-y-2">
            {top5.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </div>
      )}

      {/* Evidence Quality */}
      {sources.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
          <h3 className="mb-2 text-sm font-bold text-[var(--muted)]">Evidence Quality</h3>
          <div className="flex gap-4">
            {["nytimes.com", "rtings.com", "pcmag.com"].map((domain) => {
              const found = sources.some((s) => s.source_domain === domain && s.ok);
              return (
                <div key={domain} className="flex items-center gap-1 text-xs">
                  <span className={found ? "text-[var(--green)]" : "text-[var(--red)]"}>
                    {found ? "OK" : "X"}
                  </span>
                  <span className="text-[var(--muted)]">{domain}</span>
                </div>
              );
            })}
          </div>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {sources.filter((s) => s.ok).length}/{sources.length} sources OK
            {shortlist.length > 0 && ` | ${shortlist.length} shortlisted`}
          </p>
        </div>
      )}

      {/* Blocking Issues */}
      <IssueList
        gateFailures={gateFailures}
        warnings={warnings}
        errorMessage={run.error_message || undefined}
      />
    </div>
  );
}
