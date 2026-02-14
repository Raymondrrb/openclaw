import type { NextAction } from "@/lib/next-action";

interface Props {
  action: NextAction;
}

const bgByPriority = {
  critical: "border-orange-600 bg-orange-950/30",
  normal: "border-[var(--accent)] bg-yellow-950/20",
  info: "border-green-800 bg-green-950/20",
};

const labelByPriority = {
  critical: "ACTION REQUIRED",
  normal: "Next Step",
  info: "All Clear",
};

export function NextActionCard({ action }: Props) {
  return (
    <div className={`rounded border p-4 ${bgByPriority[action.priority]}`}>
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--accent)]">
        {labelByPriority[action.priority]}
      </p>
      <p className="text-sm">{action.action}</p>
      {action.command && (
        <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2 text-xs text-[var(--muted)]">
          {action.command}
        </pre>
      )}
    </div>
  );
}
