import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api";
import { DraftPane, Stack } from "../components/DraftPane";
import { Markdown } from "../components/Markdown";
import { useAutoScroll } from "../components/useAutoScroll";
import { VoiceSession } from "../voice";

type Msg = { role: "you" | "bot"; text: string };

const THINKING_DELAY_MS = 750;

export default function GiveFeedback() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [partial, setPartial] = useState("");
  const [pending, setPending] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [stack, setStack] = useState<Stack | null>(null);
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const textWsRef = useRef<WebSocket | null>(null);
  const voiceRef = useRef<VoiceSession | null>(null);
  const convoIdRef = useRef<string | null>(null);
  const thinkingTimerRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const voicePressStartRef = useRef<number | null>(null);
  const { ref: scrollRef, stickToBottom } = useAutoScroll<HTMLDivElement>([
    messages,
    partial,
    pending,
    showThinking,
  ]);

  function armThinkingTimer() {
    if (thinkingTimerRef.current !== null) {
      window.clearTimeout(thinkingTimerRef.current);
    }
    setShowThinking(false);
    thinkingTimerRef.current = window.setTimeout(() => {
      setShowThinking(true);
    }, THINKING_DELAY_MS);
  }

  function clearThinkingTimer() {
    if (thinkingTimerRef.current !== null) {
      window.clearTimeout(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
    setShowThinking(false);
  }

  useEffect(() => {
    // Text WS for typed turns.
    const ws = new WebSocket(wsUrl("/ws/provider"));
    ws.onopen = () => console.info("[provider WS] open");
    ws.onerror = (e) => console.error("[provider WS] error", e);
    ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    ws.onclose = (e) => {
      console.info("[provider WS] close", e.code, e.reason);
      textWsRef.current = null;
      setPending((wasPending) => {
        if (wasPending) {
          clearThinkingTimer();
          setPartial("");
          setMessages((m) => [
            ...m,
            { role: "bot", text: "(connection lost — refresh to reconnect)" },
          ]);
        }
        return false;
      });
    };
    textWsRef.current = ws;
    return () => {
      if (thinkingTimerRef.current !== null) {
        window.clearTimeout(thinkingTimerRef.current);
      }
      // Disarm callbacks before close — otherwise the async onclose from
      // StrictMode's cleanup would null out textWsRef.current which by then
      // points to the NEW WebSocket from the remount.
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleMessage(msg: { type: string; [k: string]: unknown }): void {
    switch (msg.type) {
      case "ready":
        convoIdRef.current = msg.conversation_id as string;
        break;
      case "assistant_text_delta":
        setPartial((p) => p + (msg.text as string));
        armThinkingTimer();
        break;
      case "assistant_text":
        clearThinkingTimer();
        setPartial("");
        setPending(false);
        setMessages((m) => [...m, { role: "bot", text: msg.text as string }]);
        break;
      case "draft_state":
        setStack(msg.stack as Stack);
        break;
      case "submitted":
        setMessages((m) => [
          ...m,
          { role: "bot", text: `✓ Submitted feedback ${msg.feedback_id}` },
        ]);
        break;
      case "error":
        clearThinkingTimer();
        setPartial("");
        setPending(false);
        setMessages((m) => [
          ...m,
          { role: "bot", text: `(error) ${msg.message}` },
        ]);
        break;
    }
  }

  async function send(text: string) {
    if (!text.trim() || pending) return;
    const ws = textWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("[provider WS] send while not OPEN", ws?.readyState);
      setMessages((m) => [
        ...m,
        { role: "bot", text: "(not connected — refresh the page)" },
      ]);
      return;
    }
    setMessages((m) => [...m, { role: "you", text }]);
    setDraft("");
    setPartial("");
    setPending(true);
    stickToBottom();
    armThinkingTimer();
    ws.send(JSON.stringify({ type: "user_text", text }));
    inputRef.current?.focus();
  }

  async function ensureVoice(): Promise<VoiceSession> {
    if (voiceRef.current) return voiceRef.current;
    const url =
      wsUrl("/ws/voice") +
      (convoIdRef.current ? `?conversation_id=${convoIdRef.current}` : "");
    const v = new VoiceSession(url, {
      onReady: (id) => {
        convoIdRef.current = id;
        setVoiceReady(true);
      },
      onTranscript: (t) =>
        setMessages((m) => [...m, { role: "you", text: t || "(silence)" }]),
      onAssistantText: (t) =>
        setMessages((m) => [...m, { role: "bot", text: t }]),
      onDraftState: (s) => setStack(s as Stack),
      onSubmitted: (id) =>
        setMessages((m) => [...m, { role: "bot", text: `✓ Submitted feedback ${id}` }]),
      onError: (msg) =>
        setMessages((m) => [...m, { role: "bot", text: `(error) ${msg}` }]),
    });
    await v.connect();
    voiceRef.current = v;
    return v;
  }

  async function holdToTalkStart() {
    const v = await ensureVoice();
    await v.startRecording();
    setRecording(true);
  }
  function holdToTalkStop() {
    voiceRef.current?.stopRecording();
    setRecording(false);
  }

  // Voice button supports both gestures:
  //  - short click  -> toggle on/off (release before HOLD_THRESHOLD_MS)
  //  - long press   -> record while held, stop on release
  const HOLD_THRESHOLD_MS = 250;
  async function voicePressDown() {
    if (recording) {
      // Already in toggle-on state — this press toggles off.
      holdToTalkStop();
      voicePressStartRef.current = null;
      return;
    }
    voicePressStartRef.current = Date.now();
    await holdToTalkStart();
  }
  function voicePressUp() {
    if (voicePressStartRef.current === null) return;
    const elapsed = Date.now() - voicePressStartRef.current;
    voicePressStartRef.current = null;
    if (elapsed >= HOLD_THRESHOLD_MS) {
      // Long press release — stop recording.
      holdToTalkStop();
    }
    // Else: short click — leave recording on, next click will stop.
  }
  function voicePressLeave() {
    // Cursor left the button while still pressed: treat as hold release so a
    // dragged-off click doesn't leave the mic stuck on.
    if (voicePressStartRef.current !== null && recording) {
      voicePressStartRef.current = null;
      holdToTalkStop();
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full min-h-0">
      <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-slate-400 text-sm">
              Hi! Tell me about feedback you'd like to share. You can talk
              (hold the mic) or type below.
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[80%] rounded-xl px-3 py-2 ${
                m.role === "you"
                  ? "ml-auto bg-emerald-100 text-emerald-900 text-sm whitespace-pre-wrap"
                  : "bg-slate-100 text-slate-800"
              }`}
            >
              {m.role === "bot" ? <Markdown>{m.text}</Markdown> : m.text}
            </div>
          ))}
          {partial && (
            <div className="max-w-[80%] rounded-xl px-3 py-2 bg-slate-100 text-slate-800">
              <Markdown>{partial}</Markdown>
            </div>
          )}
          {pending && showThinking && (
            <div
              className="text-slate-500 text-xs italic"
              style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
            >
              thinking…
            </div>
          )}
        </div>
        <div className="border-t border-slate-200 p-3 flex items-center gap-2">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !pending) void send(draft);
            }}
            placeholder="Type a message…"
            className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm"
          />
          <div className="flex flex-col gap-1.5">
            <button
              onMouseDown={voicePressDown}
              onMouseUp={voicePressUp}
              onMouseLeave={voicePressLeave}
              onTouchStart={voicePressDown}
              onTouchEnd={voicePressUp}
              className={`w-9 h-9 flex items-center justify-center rounded border text-base ${
                recording
                  ? "bg-rose-100 border-rose-300 text-rose-700"
                  : "bg-white border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              aria-label={recording ? "Stop recording" : "Voice"}
              title={recording ? "Stop recording" : "Click to toggle or hold"}
            >
              {recording ? "■" : "🎤"}
            </button>
            <button
              onClick={() => void send(draft)}
              disabled={pending}
              aria-label="Send"
              title="Send"
              className="w-9 h-9 flex items-center justify-center bg-slate-800 text-white rounded text-base disabled:opacity-50 hover:bg-slate-700"
            >
              ↑
            </button>
          </div>
        </div>
      </div>
      <aside className="bg-white border border-slate-200 rounded-xl p-4 min-h-0 overflow-y-auto">
        <DraftPane
          stack={stack}
          onPick={(id) =>
            void send(`Let's go back to draft ${id}.`)
          }
        />
      </aside>
    </div>
  );
}
