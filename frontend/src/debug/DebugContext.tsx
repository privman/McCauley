import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";

// Demo-time failure simulators. Kept in-memory (no localStorage) — these
// are for live demos, not preferences; persisting them would risk a user
// reopening the app stuck in a broken state and not noticing why.
//
// `networkDown`: closes any open WS and prevents the pages from
//   reconnecting until toggled off. Exercises the connection-lost /
//   not-connected user-facing recovery paths.
// `simulateMicFail`: forwarded to the voice WS in the `begin` frame.
//   The backend short-circuits transcribe() into a TranscriptError so
//   we exercise the localized spoken-apology path without needing an
//   actual STT outage.
// `simulateAnthropicOutage`: sent as a `set_outage` WS frame whenever
//   the toggle flips, plus included in user_text/begin for the per-turn
//   initial state. The backend orchestrator's step() polls the flag
//   before each LLM call and waits with exponential backoff while it's
//   true — so flipping the toggle off mid-retry lets the in-flight turn
//   recover within ~2s.
type DebugState = {
  networkDown: boolean;
  simulateMicFail: boolean;
  simulateAnthropicOutage: boolean;
};

type DebugContextValue = DebugState & {
  setNetworkDown: (v: boolean) => void;
  setSimulateMicFail: (v: boolean) => void;
  setSimulateAnthropicOutage: (v: boolean) => void;
  // Refs let imperative call sites (e.g. VoiceSession.startRecording)
  // read the *current* value without having to subscribe to context.
  networkDownRef: { readonly current: boolean };
  simulateMicFailRef: { readonly current: boolean };
  simulateAnthropicOutageRef: { readonly current: boolean };
};

const DebugContext = createContext<DebugContextValue | null>(null);

export function DebugProvider({ children }: { children: ReactNode }) {
  const [networkDown, setNetworkDownState] = useState(false);
  const [simulateMicFail, setSimulateMicFailState] = useState(false);
  const [simulateAnthropicOutage, setSimulateAnthropicOutageState] = useState(false);

  const networkDownRef = useRef(networkDown);
  const simulateMicFailRef = useRef(simulateMicFail);
  const simulateAnthropicOutageRef = useRef(simulateAnthropicOutage);

  const setNetworkDown = useCallback((v: boolean) => {
    networkDownRef.current = v;
    setNetworkDownState(v);
  }, []);
  const setSimulateMicFail = useCallback((v: boolean) => {
    simulateMicFailRef.current = v;
    setSimulateMicFailState(v);
  }, []);
  const setSimulateAnthropicOutage = useCallback((v: boolean) => {
    simulateAnthropicOutageRef.current = v;
    setSimulateAnthropicOutageState(v);
  }, []);

  return (
    <DebugContext.Provider
      value={{
        networkDown,
        simulateMicFail,
        simulateAnthropicOutage,
        setNetworkDown,
        setSimulateMicFail,
        setSimulateAnthropicOutage,
        networkDownRef,
        simulateMicFailRef,
        simulateAnthropicOutageRef,
      }}
    >
      {children}
    </DebugContext.Provider>
  );
}

export function useDebug(): DebugContextValue {
  const ctx = useContext(DebugContext);
  if (ctx === null) throw new Error("useDebug must be used inside <DebugProvider>");
  return ctx;
}
