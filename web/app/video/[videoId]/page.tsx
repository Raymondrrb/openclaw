import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getRunByVideoId,
  getNiche,
  getTop5Products,
  getAmazonProducts,
  getShortlistItems,
  getResearchSources,
  getScript,
  getAssets,
  getTTSChunks,
  getGateEvents,
} from "@/lib/queries";
import { computeNextAction, computeWarnings } from "@/lib/next-action";
import { NextActionCard } from "@/components/next-action-card";
import { StagePipeline } from "@/components/stage-pipeline";
import { ProductCard } from "@/components/product-card";
import { IssueList } from "@/components/issue-list";

const STAGES = ["niche", "research", "verify", "rank", "script", "assets", "tts", "manifest"];

const statusColor: Record<string, string> = {
  running: "bg-yellow-900/40 text-[var(--yellow)]",
  complete: "bg-green-900/40 text-[var(--green)]",
  failed: "bg-red-900/40 text-[var(--red)]",
  aborted: "bg-red-900/40 text-[var(--red)]",
};

export const dynamic = "force-dynamic";

export default async function VideoDetailPage({
  params,
}: {
  params: Promise<{ videoId: string }>;
}) {
  const { videoId } = await params;
  const run = await getRunByVideoId(videoId);
  if (!run) notFound();

  const [niche, top5, amazonProducts, shortlist, sources, script, assets, ttsChunks, gateEvents] =
    await Promise.all([
      getNiche(run.id),
      getTop5Products(run.id),
      getAmazonProducts(run.id),
      getShortlistItems(run.id),
      getResearchSources(run.id),
      getScript(run.id),
      getAssets(run.id),
      getTTSChunks(run.id),
      getGateEvents(run.id),
    ]);

  const nextAction = computeNextAction(run, script);
  const warnings = computeWarnings({ shortlist, amazonProducts, top5, sources, script, niche });
  const gateFailures = gateEvents.filter((e) => e.event_type === "gate_fail");
  const completed = new Set(run.stages_completed ?? []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
        <Link href="/" className="hover:text-[var(--fg)]">Home</Link>
        <span>/</span>
        <Link href="/runs" className="hover:text-[var(--fg)]">Runs</Link>
        <span>/</span>
        <span className="text-[var(--fg)]">{videoId}</span>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{videoId}</h1>
          <p className="text-sm text-[var(--muted)]">
            {run.cluster}
            {niche?.subcategory ? ` / ${niche.subcategory}` : ""}
          </p>
        </div>
        <div className="text-right">
          <span className={`inline-block rounded px-2 py-1 text-xs font-medium ${statusColor[run.status] ?? ""}`}>
            {run.status}
          </span>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Created {new Date(run.created_at).toLocaleString()}
          </p>
          <p className="text-xs text-[var(--muted)]">
            Updated {new Date(run.updated_at).toLocaleString()}
          </p>
        </div>
      </div>

      <NextActionCard action={nextAction} />

      {/* Stage Timeline */}
      <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
        <h3 className="mb-3 text-sm font-bold text-[var(--muted)]">Pipeline Stages</h3>
        <StagePipeline
          stagesCompleted={run.stages_completed}
          currentStatus={run.status}
          gateEvents={gateEvents}
        />
        <div className="mt-4 space-y-2">
          {STAGES.map((stage) => {
            const stageEvents = gateEvents.filter((e) => e.stage === stage);
            const gate = stageEvents.find(
              (e) => e.event_type === "gate_pass" || e.event_type === "gate_fail"
            );
            return (
              <div key={stage} className="flex items-center gap-3 text-xs">
                <span className={`w-16 ${completed.has(stage) ? "text-[var(--green)]" : "text-[var(--muted)]"}`}>
                  {completed.has(stage) ? "done" : "pending"}
                </span>
                <span className="w-20 font-medium">{stage}</span>
                {gate && (
                  <span className={gate.event_type === "gate_pass" ? "text-[var(--green)]" : "text-[var(--red)]"}>
                    {gate.event_type === "gate_pass" ? "PASS" : "FAIL"}
                    {gate.payload && (gate.payload as Record<string, unknown>).reason
                      ? `: ${String((gate.payload as Record<string, unknown>).reason)}`
                      : ""}
                  </span>
                )}
                {stageEvents.length > 0 && (
                  <span className="text-[var(--muted)]">
                    {new Date(stageEvents[stageEvents.length - 1].created_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Research Report */}
      {sources.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
          <h3 className="mb-3 text-sm font-bold text-[var(--muted)]">Research Sources</h3>
          <div className="space-y-1">
            {sources.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-xs">
                <span className={s.ok ? "text-[var(--green)]" : "text-[var(--red)]"}>
                  {s.ok ? "OK" : "ERR"}
                </span>
                <span className="text-[var(--muted)]">{s.source_domain}</span>
                <span className="truncate text-[var(--muted)]">{s.source_url}</span>
              </div>
            ))}
          </div>

          {shortlist.length > 0 && (
            <>
              <h4 className="mb-2 mt-4 text-xs font-bold text-[var(--muted)]">
                Shortlist ({shortlist.length})
              </h4>
              <div className="space-y-1">
                {shortlist.map((item) => (
                  <div key={item.id} className="flex items-center gap-2 text-xs">
                    <span className="w-4 text-right text-[var(--muted)]">
                      {item.candidate_rank}
                    </span>
                    <span>{item.product_name_clean}</span>
                    {item.buyer_pain_fit && (
                      <span className="text-[var(--muted)]">({item.buyer_pain_fit})</span>
                    )}
                    <span
                      className={
                        item.passed_domain_policy ? "text-[var(--green)]" : "text-[var(--red)]"
                      }
                    >
                      {item.passed_domain_policy ? "policy OK" : "policy FAIL"}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Products */}
      {top5.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-bold text-[var(--muted)]">Top 5 Products</h3>
          <div className="space-y-2">
            {top5.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>

          {amazonProducts.length > 0 && (
            <>
              <h4 className="mb-2 mt-4 text-xs font-bold text-[var(--muted)]">
                Amazon Verification ({amazonProducts.length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                      <th className="pb-1 pr-3">ASIN</th>
                      <th className="pb-1 pr-3">Title</th>
                      <th className="pb-1 pr-3">Price</th>
                      <th className="pb-1 pr-3">Rating</th>
                      <th className="pb-1 pr-3">Reviews</th>
                      <th className="pb-1 pr-3">Stock</th>
                      <th className="pb-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {amazonProducts.map((ap) => (
                      <tr key={ap.id} className="border-b border-[var(--border)]">
                        <td className="py-1 pr-3 font-mono">{ap.asin}</td>
                        <td className="max-w-[200px] truncate py-1 pr-3">{ap.amazon_title}</td>
                        <td className="py-1 pr-3">
                          {ap.price !== null ? `$${ap.price}` : "-"}
                        </td>
                        <td className="py-1 pr-3">
                          {ap.rating !== null ? ap.rating : "-"}
                        </td>
                        <td className="py-1 pr-3">{ap.review_count}</td>
                        <td className="py-1 pr-3">
                          <span className={ap.in_stock ? "text-[var(--green)]" : "text-[var(--red)]"}>
                            {ap.in_stock ? "Yes" : "No"}
                          </span>
                        </td>
                        <td className="py-1">
                          {ap.rejected ? (
                            <span className="text-[var(--red)]">{ap.reject_reason || "rejected"}</span>
                          ) : (
                            <span className="text-[var(--green)]">OK</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* Script Status */}
      {script && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
          <h3 className="mb-2 text-sm font-bold text-[var(--muted)]">Script</h3>
          <div className="flex flex-wrap gap-3 text-xs">
            <span>
              Status:{" "}
              <span className="font-medium text-[var(--accent)]">{script.status}</span>
            </span>
            <span>Words: {script.word_count}</span>
            <span>
              Disclosure:{" "}
              <span className={script.has_disclosure ? "text-[var(--green)]" : "text-[var(--red)]"}>
                {script.has_disclosure ? "Yes" : "No"}
              </span>
            </span>
          </div>
          {script.brief_text && (
            <pre className="mt-2 max-h-32 overflow-y-auto rounded bg-black/30 p-2 text-xs text-[var(--muted)]">
              {script.brief_text.slice(0, 500)}
              {script.brief_text.length > 500 ? "..." : ""}
            </pre>
          )}
        </div>
      )}

      {/* Assets */}
      {assets.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
          <h3 className="mb-2 text-sm font-bold text-[var(--muted)]">
            Assets ({assets.filter((a) => a.ok).length}/{assets.length} OK)
          </h3>
          <div className="space-y-1">
            {assets.map((a) => (
              <div key={a.id} className="flex items-center gap-2 text-xs">
                <span className={a.ok ? "text-[var(--green)]" : "text-[var(--red)]"}>
                  {a.ok ? "OK" : "ERR"}
                </span>
                <span>{a.asset_type}</span>
                <span className="text-[var(--muted)]">{a.product_asin}</span>
                {a.storage_path && (
                  <span className="truncate text-[var(--muted)]">{a.storage_path}</span>
                )}
                {a.error && <span className="text-[var(--red)]">{a.error}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TTS Audio */}
      {ttsChunks.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
          <h3 className="mb-2 text-sm font-bold text-[var(--muted)]">
            TTS Audio ({ttsChunks.filter((c) => c.ok).length}/{ttsChunks.length} OK)
          </h3>
          <p className="mb-2 text-xs text-[var(--muted)]">
            Total duration:{" "}
            {ttsChunks
              .reduce((sum, c) => sum + Number(c.duration_seconds), 0)
              .toFixed(1)}
            s
          </p>
          <div className="space-y-1">
            {ttsChunks.map((c) => (
              <div key={c.id} className="flex items-center gap-2 text-xs">
                <span className={c.ok ? "text-[var(--green)]" : "text-[var(--red)]"}>
                  {c.ok ? "OK" : "ERR"}
                </span>
                <span className="text-[var(--muted)]">#{c.chunk_index}</span>
                <span>{Number(c.duration_seconds).toFixed(1)}s</span>
                {c.error && <span className="text-[var(--red)]">{c.error}</span>}
              </div>
            ))}
          </div>
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
