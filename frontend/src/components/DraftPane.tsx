type Subject = { kind: string; id: string | null; name: string | null };
type SBI = {
  idx: number;
  situation: string | null;
  behavior: string | null;
  impact: string | null;
  complete: boolean;
};
export type Draft = {
  local_id: string;
  subject: Subject | null;
  headline: string | null;
  is_anonymous: boolean;
  sbis: SBI[];
};
export type Stack = { current: Draft | null; paused: Draft[] };

export function DraftPane({
  stack,
  onPick,
}: {
  stack: Stack | null;
  onPick: (local_id: string) => void;
}) {
  if (!stack) {
    return <div className="text-sm text-slate-400">No drafts yet — start talking.</div>;
  }
  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-xs uppercase font-medium text-slate-500 mb-2">
          Drafts in this session
        </h3>
        <ul className="space-y-1">
          {stack.current && (
            <li>
              <DraftRow draft={stack.current} status="current" onPick={onPick} />
            </li>
          )}
          {stack.paused.map((d) => (
            <li key={d.local_id}>
              <DraftRow draft={d} status="paused" onPick={onPick} />
            </li>
          ))}
        </ul>
      </section>
      {stack.current && (
        <section>
          <h3 className="text-xs uppercase font-medium text-slate-500 mb-2">
            Current draft ({stack.current.local_id})
          </h3>
          <DraftDetail draft={stack.current} />
        </section>
      )}
    </div>
  );
}

function DraftRow({
  draft,
  status,
  onPick,
}: {
  draft: Draft;
  status: "current" | "paused";
  onPick: (local_id: string) => void;
}) {
  const label =
    draft.subject?.name ?? draft.headline ?? `Draft ${draft.local_id}`;
  return (
    <button
      onClick={() => onPick(draft.local_id)}
      className={`w-full text-left px-2 py-1.5 rounded text-sm flex items-center gap-2 ${
        status === "current"
          ? "bg-emerald-50 text-emerald-900"
          : "text-slate-700 hover:bg-slate-50"
      }`}
    >
      <span className={status === "current" ? "text-emerald-600" : "text-slate-300"}>
        {status === "current" ? "●" : "○"}
      </span>
      <span className="truncate">{label}</span>
    </button>
  );
}

function DraftDetail({ draft }: { draft: Draft }) {
  return (
    <div className="text-sm space-y-3">
      <KV k="Subject" v={draft.subject?.name ?? "—"} />
      <KV k="Point" v={draft.headline ?? "—"} />
      <KV k="Anonymous" v={draft.is_anonymous ? "yes" : "no"} />
      <div>
        <div className="text-xs uppercase font-medium text-slate-500 mb-1">Examples</div>
        {draft.sbis.length === 0 && <div className="text-slate-400">none yet</div>}
        <ul className="space-y-2">
          {draft.sbis.map((s) => (
            <li key={s.idx} className="border border-slate-200 rounded p-2">
              <div className="font-medium text-slate-700 text-xs mb-1">
                #{s.idx + 1} {s.complete ? "● complete" : "… in progress"}
              </div>
              <KV k="S" v={s.situation ?? "—"} small />
              <KV k="B" v={s.behavior ?? "—"} small />
              <KV k="I" v={s.impact ?? "—"} small />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function KV({ k, v, small }: { k: string; v: string; small?: boolean }) {
  return (
    <div className={`flex gap-3 ${small ? "text-xs" : ""}`}>
      <div className="text-slate-500 w-16 shrink-0">{k}</div>
      <div className="text-slate-800 break-words">{v}</div>
    </div>
  );
}
