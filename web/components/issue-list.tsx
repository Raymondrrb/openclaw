import type { ConstraintWarning } from "@/lib/next-action";
import type { AgentEvent } from "@/lib/types";

interface Props {
  gateFailures: AgentEvent[];
  warnings: ConstraintWarning[];
  errorMessage?: string;
}

export function IssueList({ gateFailures, warnings, errorMessage }: Props) {
  const hasIssues = gateFailures.length > 0 || warnings.length > 0 || errorMessage;
  if (!hasIssues) return null;

  return (
    <div className="rounded border border-red-900/50 bg-red-950/20 p-4">
      <h3 className="mb-3 text-sm font-bold text-[var(--red)]">Blocking Issues</h3>

      {errorMessage && (
        <div className="mb-2 rounded bg-red-950/30 p-2 text-xs text-[var(--red)]">
          Pipeline error: {errorMessage}
        </div>
      )}

      {gateFailures.map((e) => (
        <div key={e.id} className="mb-2 rounded bg-red-950/30 p-2 text-xs">
          <span className="font-medium text-[var(--red)]">[{e.stage}]</span>{" "}
          <span className="text-[var(--muted)]">{e.agent_name}:</span>{" "}
          {String((e.payload as Record<string, unknown>).reason ?? JSON.stringify(e.payload))}
        </div>
      ))}

      {warnings.map((w, i) => (
        <div key={i} className="mb-1 text-xs text-[var(--yellow)]">
          {w.message}
        </div>
      ))}
    </div>
  );
}
