import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api";
import { DraftPane, Stack } from "../components/DraftPane";
import { VoiceSession } from "../voice";

type Msg = { role: "you" | "bot"; text: string };

export default function GiveFeedback() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [stack, setStack] = useState<Stack | null>(null);
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const textWsRef = useRef<WebSocket | null>(null);
  const voiceRef = useRef<VoiceSession | null>(null);
  const convoIdRef = useRef<string | null>(null);

  useEffect(() => {
    // Text WS for typed turns.
    const ws = new WebSocket(wsUrl("/ws/provider"));
    ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    ws.onclose = () => (textWsRef.current = null);
    textWsRef.current = ws;
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleMessage(msg: { type: string; [k: string]: unknown }): void {
    switch (msg.type) {
      case "ready":
        convoIdRef.current = msg.conversation_id as string;
        break;
      case "assistant_text":
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
        setMessages((m) => [
          ...m,
          { role: "bot", text: `(error) ${msg.message}` },
        ]);
        break;
    }
  }

  async function send(text: string) {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "you", text }]);
    setDraft("");
    textWsRef.current?.send(JSON.stringify({ type: "user_text", text }));
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full min-h-0">
      <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-slate-400 text-sm">
              Hi! Tell me about feedback you'd like to share. You can talk
              (hold the mic) or type below.
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
                m.role === "you"
                  ? "ml-auto bg-emerald-100 text-emerald-900"
                  : "bg-slate-100 text-slate-800"
              }`}
            >
              {m.text}
            </div>
          ))}
        </div>
        <div className="border-t border-slate-200 p-3 flex items-center gap-2">
          <button
            onMouseDown={holdToTalkStart}
            onMouseUp={holdToTalkStop}
            onMouseLeave={recording ? holdToTalkStop : undefined}
            onTouchStart={holdToTalkStart}
            onTouchEnd={holdToTalkStop}
            className={`px-3 py-2 rounded text-sm border ${
              recording
                ? "bg-rose-100 border-rose-300 text-rose-700"
                : "bg-white border-slate-300 text-slate-700"
            }`}
            aria-label="Hold to talk"
            title={voiceReady ? "Hold to talk" : "Hold to start voice session"}
          >
            {recording ? "● recording…" : "🎤 hold to talk"}
          </button>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void send(draft);
            }}
            placeholder="…or type a message"
            className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm"
          />
          <button
            onClick={() => void send(draft)}
            className="px-3 py-2 bg-slate-800 text-white rounded text-sm"
          >
            Send
          </button>
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
