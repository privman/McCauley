import { Fragment } from "react";

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
  is_empty?: boolean;
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
  // Hide drafts the user hasn't put any real content into yet — those are
  // just unused workspaces, not real items worth displaying.
  const current = stack && stack.current && !stack.current.is_empty ? stack.current : null;
  const paused = stack ? stack.paused.filter((d) => !d.is_empty) : [];
  const hasAnyDraft = current !== null || paused.length > 0;

  if (!hasAnyDraft) {
    return <div className="text-sm text-slate-400">No drafts yet — start talking.</div>;
  }
  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-xs uppercase font-medium text-slate-500 mb-2">
          Drafts in this session
        </h3>
        <ul className="space-y-1">
          {current && (
            <li>
              <DraftRow draft={current} status="current" onPick={onPick} />
            </li>
          )}
          {paused.map((d) => (
            <li key={d.local_id}>
              <DraftRow draft={d} status="paused" onPick={onPick} />
            </li>
          ))}
        </ul>
      </section>
      {current && (
        <section>
          <h3 className="text-xs uppercase font-medium text-slate-500 mb-2">
            Current draft ({current.local_id})
          </h3>
          <DraftDetail draft={current} />
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
    <div className="text-sm space-y-4">
      <KVGrid
        rows={[
          ["Subject", draft.subject?.name ?? "—"],
          ["Point", draft.headline ?? "—"],
          ["Anonymous", draft.is_anonymous ? "yes" : "no"],
        ]}
      />
      <div>
        <div className="text-xs uppercase font-medium text-slate-500 mb-2">Examples</div>
        {draft.sbis.length === 0 && <div className="text-slate-400">none yet</div>}
        <ul className="space-y-2">
          {draft.sbis.map((s) => (
            <li key={s.idx} className="border border-slate-200 rounded p-2 space-y-2">
              <div className="font-medium text-slate-700 text-xs">
                #{s.idx + 1} {s.complete ? "● complete" : "… in progress"}
              </div>
              <KVGrid
                small
                rows={[
                  ["S", s.situation ?? "—"],
                  ["B", s.behavior ?? "—"],
                  ["I", s.impact ?? "—"],
                ]}
              />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function KVGrid({
  rows,
  small,
}: {
  rows: [string, string][];
  small?: boolean;
}) {
  return (
    <dl
      className={`grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 ${
        small ? "text-xs" : ""
      }`}
    >
      {rows.map(([k, v]) => (
        <Fragment key={k}>
          <dt className="text-slate-500">{k}</dt>
          <dd className="text-slate-800 break-words">{v}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
