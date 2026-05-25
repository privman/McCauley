import { useState } from "react";
import { useDebug } from "../debug/DebugContext";

// Floating bottom-right panel with two demo-time failure simulators.
// Always visible (the app is a demo build), but collapsed to a single
// chip so it doesn't crowd the chat UI.
export function DebugPanel() {
  const { networkDown, simulateMicFail, setNetworkDown, setSimulateMicFail } = useDebug();
  const [open, setOpen] = useState(false);
  const anyActive = networkDown || simulateMicFail;

  return (
    <div className="fixed bottom-3 right-3 z-50">
      {open ? (
        <div className="w-64 rounded-lg border border-dashed border-amber-400 bg-amber-50/95 shadow-md p-3 text-xs text-amber-900">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold uppercase tracking-wider">Debug</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close debug panel"
              className="text-amber-700 hover:text-amber-900"
            >
              ×
            </button>
          </div>
          <ToggleRow
            label="Simulate network drop"
            description="Close WS, refuse new connections."
            value={networkDown}
            onChange={setNetworkDown}
          />
          <ToggleRow
            label="Simulate mic failure"
            description="Next utterance returns an STT error."
            value={simulateMicFail}
            onChange={setSimulateMicFail}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-dashed text-xs font-semibold shadow-sm ${
            anyActive
              ? "border-amber-500 bg-amber-100 text-amber-900"
              : "border-slate-300 bg-white/90 text-slate-500 hover:bg-slate-50"
          }`}
          aria-label="Open debug panel"
          title={anyActive ? "Debug overrides active" : "Open debug panel"}
        >
          <span>debug</span>
          {anyActive && <span aria-hidden>●</span>}
        </button>
      )}
    </div>
  );
}

function ToggleRow({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 py-1 cursor-pointer">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-amber-600"
      />
      <span className="flex-1">
        <span className="block font-medium">{label}</span>
        <span className="block text-amber-700/80 text-[11px]">{description}</span>
      </span>
    </label>
  );
}
