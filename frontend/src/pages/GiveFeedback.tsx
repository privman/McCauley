import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api";
import { DraftPane, Stack } from "../components/DraftPane";
import { Markdown } from "../components/Markdown";
import { useAutoScroll } from "../components/useAutoScroll";
import { useLocale } from "../i18n/LocaleContext";
import { VoiceSession } from "../voice";

// `isGreeting` flags the auto-greeting so we can replace it when the
// locale changes — but only as long as it's still the only message.
// `system` is for technical notifications (errors, submitted, etc.) —
// rendered in the same italic-dim style as the "thinking…" indicator
// rather than as a chat bubble, since they describe app/server events
// rather than something a participant said.
type Msg = { role: "you" | "bot" | "system"; text: string; isGreeting?: boolean };

const THINKING_DELAY_MS = 750;

// User-facing voice playback speeds. 1 is the default brisk pace; the
// backend multiplies by 1.2 internally to land at Google's `speaking_rate`.
const VOICE_SPEEDS = [0.5, 0.75, 1, 1.1, 1.25, 1.5, 1.75, 2] as const;

export default function GiveFeedback() {
  const { locale, t } = useLocale();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [partial, setPartial] = useState("");
  const [pending, setPending] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  // "reconnecting" covers both intentional debug-panel disconnect and a
  // real WS close; the indicator clears when the next WS open succeeds.
  const [connectionStatus, setConnectionStatus] = useState<"connected" | "reconnecting">(
    "connected",
  );
  const [stack, setStack] = useState<Stack | null>(null);
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [voiceStarting, setVoiceStarting] = useState(false);
  const [_voiceReady, setVoiceReady] = useState(false);
  const [voiceSpeed, setVoiceSpeed] = useState<number>(1);
  const textWsRef = useRef<WebSocket | null>(null);
  const voiceRef = useRef<VoiceSession | null>(null);
  const convoIdRef = useRef<string | null>(null);
  const voicePressStartRef = useRef<number | null>(null);
  const thinkingTimerRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  // Latest locale, captured for callbacks that close over stale state
  // (the WS onmessage / onclose handlers, mostly). Updated via the
  // effect below.
  const localeRef = useRef(locale);
  useEffect(() => {
    localeRef.current = locale;
  }, [locale]);
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
    // Text WS for typed turns. The locale query param is consumed by
    // the backend to render the localized greeting frame; per-message
    // locale on user_text frames keeps later turns in sync. Passing
    // `conversation_id` on reconnect makes the backend resume the same
    // convo row — so we don't get a duplicate greeting on top of the
    // existing chat. convoIdRef is populated from the first `ready`
    // frame and only cleared on a locale change (the stale-greeting
    // refresh effect below).
    const ws = new WebSocket(
      wsUrl("/ws/provider", {
        locale: localeRef.current,
        conversation_id: convoIdRef.current ?? undefined,
      }),
    );
    ws.onopen = () => {
      console.info("[provider WS] open");
      setConnectionStatus("connected");
    };
    ws.onerror = (e) => console.error("[provider WS] error", e);
    ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    ws.onclose = (e) => {
      console.info("[provider WS] close", e.code, e.reason);
      textWsRef.current = null;
      // Surface the dropped socket — the user-facing message is the
      // status indicator below the chat, not a chat bubble. Pending
      // turns are abandoned (no response is coming).
      setConnectionStatus("reconnecting");
      setPending(false);
      clearThinkingTimer();
      setPartial("");
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
        setMessages((m) => {
          // The first bot frame on a fresh conversation IS the
          // hardcoded greeting; tag it so a later locale change can
          // replace it if the user hasn't typed yet.
          const isGreeting = m.length === 0;
          return [...m, { role: "bot", text: msg.text as string, isGreeting }];
        });
        break;
      case "draft_state":
        setStack(msg.stack as Stack);
        break;
      case "submitted":
        setMessages((m) => [
          ...m,
          { role: "system", text: `${t("give.submitted")} ${msg.feedback_id}` },
        ]);
        break;
      case "error":
        clearThinkingTimer();
        setPartial("");
        setPending(false);
        setMessages((m) => [
          ...m,
          { role: "system", text: `${t("give.error_prefix")} ${msg.message}` },
        ]);
        break;
    }
  }

  // Stale-greeting refresh: if the locale changes while the auto-greeting
  // is still the only message, ask the backend to re-send a localized
  // greeting. Once the user has typed anything, leave the original
  // greeting alone (replacing it mid-conversation would feel weird).
  useEffect(() => {
    if (messages.length !== 1) return;
    if (!messages[0].isGreeting) return;
    // Reopen the WS with the new locale. The backend treats a connect
    // without `conversation_id` as a new conversation and sends a fresh
    // greeting frame in the new language. The next `assistant_text`
    // frame will replace the stale one in our state.
    const ws = textWsRef.current;
    if (!ws) return;
    setMessages([]);
    convoIdRef.current = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
    ws.close();
    const next = new WebSocket(wsUrl("/ws/provider", { locale }));
    next.onopen = () => console.info("[provider WS] reopen for locale change");
    next.onerror = (e) => console.error("[provider WS] error", e);
    next.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    next.onclose = (e) => {
      console.info("[provider WS] close", e.code, e.reason);
      textWsRef.current = null;
    };
    textWsRef.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  async function send(text: string) {
    if (!text.trim() || pending) return;
    const ws = textWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // The connection-failed indicator is already visible — no need
      // to spam the chat with a duplicate notice. Silently drop the
      // send so the input keeps the user's text for retry.
      console.warn("[provider WS] send while not OPEN", ws?.readyState);
      return;
    }
    // Any new user message — typed, button-synthesized, or otherwise —
    // should kill any in-flight TTS audio from the previous turn.
    voiceRef.current?.stopPlayback();
    setMessages((m) => [...m, { role: "you", text }]);
    setDraft("");
    setPartial("");
    setPending(true);
    stickToBottom();
    armThinkingTimer();
    ws.send(JSON.stringify({ type: "user_text", text, locale }));
    inputRef.current?.focus();
  }

  async function ensureVoice(): Promise<VoiceSession> {
    if (voiceRef.current) return voiceRef.current;
    const url = wsUrl("/ws/voice", {
      conversation_id: convoIdRef.current ?? undefined,
      locale,
    });
    const v = new VoiceSession(
      url,
      {
        onReady: (id) => {
          convoIdRef.current = id;
          setVoiceReady(true);
        },
        onTranscript: (raw) =>
          setMessages((m) => [...m, { role: "you", text: raw || t("give.silence") }]),
        onAssistantTextDelta: (chunk) => {
          setPartial((p) => p + chunk);
          armThinkingTimer();
        },
        onAssistantText: (txt) => {
          clearThinkingTimer();
          setPartial("");
          setMessages((m) => [...m, { role: "bot", text: txt }]);
        },
        onDraftState: (s) => setStack(s as Stack),
        onSubmitted: (id) =>
          setMessages((m) => [...m, { role: "system", text: `${t("give.submitted")} ${id}` }]),
        onError: (msg) => {
          clearThinkingTimer();
          setPartial("");
          setMessages((m) => [...m, { role: "system", text: `${t("give.error_prefix")} ${msg}` }]);
        },
      },
      locale,
    );
    await v.connect();
    v.setSpeed(voiceSpeed);
    voiceRef.current = v;
    return v;
  }

  // Propagate locale flips to an already-open voice session so the next
  // `begin` frame carries the right code (and the agent's reply comes
  // back in the new language and voice).
  useEffect(() => {
    voiceRef.current?.setLocale(locale);
  }, [locale]);

  function changeVoiceSpeed(speed: number) {
    setVoiceSpeed(speed);
    voiceRef.current?.setSpeed(speed);
  }

  async function holdToTalkStart() {
    setVoiceStarting(true);
    try {
      const v = await ensureVoice();
      await v.startRecording();
      setRecording(true);
    } finally {
      // Cleared whether startup succeeded or threw — on failure the
      // button reverts to idle; on success the recording=red state
      // takes over.
      setVoiceStarting(false);
    }
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
    // Kill any in-flight TTS audio immediately so the agent doesn't
    // hear itself if the user starts talking before playback finished.
    // Safe no-op if there's no active VoiceSession yet.
    voiceRef.current?.stopPlayback();
    // Ignore a second press while we're still spinning up — otherwise
    // we'd double-start getUserMedia.
    if (voiceStarting) return;
    if (recording) {
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
      holdToTalkStop();
    }
  }
  function voicePressLeave() {
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
            <div className="text-slate-400 text-sm">{t("give.empty_hint")}</div>
          )}
          {messages.map((m, i) => {
            if (m.role === "system") {
              return (
                <div
                  key={i}
                  className="text-slate-500 text-xs italic"
                  style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
                >
                  {m.text}
                </div>
              );
            }
            return (
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
            );
          })}
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
              {t("give.thinking")}
            </div>
          )}
          {connectionStatus === "reconnecting" && (
            <div
              className="text-slate-500 text-xs italic"
              style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
            >
              {t("system.connection_retrying")}
            </div>
          )}
        </div>
        <div className="border-t border-slate-200 p-3 flex items-stretch gap-2">
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter inserts a newline (standard chat UX).
              if (e.key === "Enter" && !e.shiftKey && !pending) {
                e.preventDefault();
                void send(draft);
              }
            }}
            rows={3}
            placeholder={t("give.placeholder")}
            className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm resize-none overflow-y-auto"
          />
          <div className="flex flex-col gap-1.5">
            <select
              value={voiceSpeed}
              onChange={(e) => changeVoiceSpeed(Number(e.target.value))}
              aria-label={t("give.voice_speed_label")}
              title={t("give.voice_speed_label")}
              className="w-14 h-7 px-1 border border-slate-300 rounded text-xs text-slate-700 bg-white hover:bg-slate-50"
            >
              {VOICE_SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
            <button
              onMouseDown={voicePressDown}
              onMouseUp={voicePressUp}
              onMouseLeave={voicePressLeave}
              onTouchStart={voicePressDown}
              onTouchEnd={voicePressUp}
              className={`w-14 h-7 flex items-center justify-center rounded border text-sm ${
                recording
                  ? "bg-rose-100 border-rose-300 text-rose-700"
                  : voiceStarting
                    ? "bg-slate-50 border-slate-300 text-slate-500"
                    : "bg-white border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              aria-label={
                voiceStarting
                  ? t("give.voice_aria_starting")
                  : recording
                    ? t("give.voice_aria_stop")
                    : t("give.voice_aria_default")
              }
              title={
                voiceStarting
                  ? t("give.voice_title_starting")
                  : recording
                    ? t("give.voice_title_stop")
                    : t("give.voice_title_default")
              }
            >
              {voiceStarting ? (
                <span
                  aria-hidden
                  className="inline-block w-3.5 h-3.5 border-2 border-slate-300 border-t-slate-700 rounded-full animate-spin"
                />
              ) : recording ? (
                "■"
              ) : (
                "🎤"
              )}
            </button>
            <button
              onClick={() => void send(draft)}
              disabled={pending}
              aria-label={t("give.send")}
              title={t("give.send")}
              className="w-14 h-7 flex items-center justify-center bg-slate-800 text-white rounded text-sm hover:bg-slate-700 disabled:opacity-50"
            >
              ↑
            </button>
          </div>
        </div>
      </div>
      <aside className="bg-white border border-slate-200 rounded-xl p-4 min-h-0 overflow-y-auto">
        <DraftPane
          stack={stack}
          disabled={pending}
          onPick={(id) => void send(`${t("give.resume_message")} ${id}.`)}
          onToggleAnonymous={(_id, value) =>
            void send(value ? t("give.anonymity_on") : t("give.anonymity_off"))
          }
          onAddExample={() => void send(t("give.add_example_message"))}
          onSubmit={() => void send(t("give.submit_message"))}
        />
      </aside>
    </div>
  );
}
