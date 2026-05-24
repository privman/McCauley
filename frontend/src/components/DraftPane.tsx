import { Fragment, ReactNode } from "react";

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
  onToggleAnonymous,
  onAddExample,
  onSubmit,
  disabled,
}: {
  stack: Stack | null;
  onPick: (local_id: string) => void;
  onToggleAnonymous: (local_id: string, value: boolean) => void;
  onAddExample: (local_id: string) => void;
  onSubmit: (local_id: string) => void;
  disabled?: boolean;
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
          <DraftDetail
            draft={current}
            onToggleAnonymous={onToggleAnonymous}
            onAddExample={onAddExample}
            onSubmit={onSubmit}
            disabled={disabled}
          />
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

function DraftDetail({
  draft,
  onToggleAnonymous,
  onAddExample,
  onSubmit,
  disabled,
}: {
  draft: Draft;
  onToggleAnonymous: (local_id: string, value: boolean) => void;
  onAddExample: (local_id: string) => void;
  onSubmit: (local_id: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="text-sm space-y-4">
      <KVGrid
        rows={[
          ["Subject", draft.subject?.name ?? "—"],
          ["Point", draft.headline ?? "—"],
          [
            "Anonymous",
            <AnonymousToggle
              key="anon"
              value={draft.is_anonymous}
              disabled={disabled}
              onChange={(v) => onToggleAnonymous(draft.local_id, v)}
            />,
          ],
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
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={() => onAddExample(draft.local_id)}
          disabled={disabled}
          className="flex-1 px-3 py-1.5 text-xs rounded border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          + Add example
        </button>
        <button
          type="button"
          onClick={() => onSubmit(draft.local_id)}
          disabled={disabled}
          className="flex-1 px-3 py-1.5 text-xs rounded bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Submit
        </button>
      </div>
    </div>
  );
}

function KVGrid({
  rows,
  small,
}: {
  rows: [string, ReactNode][];
  small?: boolean;
}) {
  return (
    <dl
      className={`grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 items-center ${
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

function AnonymousToggle({
  value,
  disabled,
  onChange,
}: {
  value: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      disabled={disabled}
      onClick={() => onChange(!value)}
      title={disabled ? "Wait for the agent to finish" : "Toggle anonymity"}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
        value ? "bg-emerald-500" : "bg-slate-300"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          value ? "translate-x-[18px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}
