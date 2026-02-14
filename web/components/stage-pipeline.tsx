import type { AgentEvent } from "@/lib/types";

const STAGES = ["niche", "research", "verify", "rank", "script", "assets", "tts", "manifest"];

interface Props {
  stagesCompleted: string[];
  currentStatus: string;
  gateEvents: AgentEvent[];
}

function stageColor(
  stage: string,
  completed: Set<string>,
  failed: Set<string>,
  currentStatus: string
): string {
  if (failed.has(stage)) return "bg-[var(--red)]";
  if (completed.has(stage)) return "bg-[var(--green)]";
  // First incomplete stage is "in progress" if pipeline is running
  const firstIncomplete = STAGES.find((s) => !completed.has(s));
  if (stage === firstIncomplete && currentStatus === "running") return "bg-[var(--yellow)]";
  return "bg-[var(--border)]";
}

export function StagePipeline({ stagesCompleted, currentStatus, gateEvents }: Props) {
  const completed = new Set(stagesCompleted);
  const failed = new Set(
    gateEvents
      .filter((e) => e.event_type === "gate_fail")
      .map((e) => e.stage)
  );

  return (
    <div className="flex items-center gap-1">
      {STAGES.map((stage, i) => (
        <div key={stage} className="flex items-center">
          <div className="flex flex-col items-center">
            <div
              className={`h-3 w-3 rounded-full ${stageColor(stage, completed, failed, currentStatus)}`}
              title={stage}
            />
            <span className="mt-1 text-[10px] text-[var(--muted)]">{stage}</span>
          </div>
          {i < STAGES.length - 1 && (
            <div className="mx-1 h-px w-4 bg-[var(--border)]" />
          )}
        </div>
      ))}
    </div>
  );
}
