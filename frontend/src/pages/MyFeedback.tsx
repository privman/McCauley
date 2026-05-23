import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api";
import { Markdown } from "../components/Markdown";
import { useAutoScroll } from "../components/useAutoScroll";

type Msg = { role: "you" | "bot"; text: string };
type Source = {
  id: string;
  headline: string;
  subject: string | null;
  submitted_at: string | null;
};

const EXAMPLE_PROMPTS = [
  "What feedback came in about my reports this month?",
  "Summarise feedback about Priya.",
  "Generate a report on the Mobile team in Q1.",
  "What are the top themes in feedback about delivery?",
];

const THINKING_DELAY_MS = 750;

export default function MyFeedback() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [partial, setPartial] = useState("");
  const [pending, setPending] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [draft, setDraft] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const thinkingTimerRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
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
    const ws = new WebSocket(wsUrl("/ws/recipient"));
    ws.onopen = () => console.info("[recipient WS] open");
    ws.onerror = (e) => console.error("[recipient WS] error", e);
    ws.onclose = (e) => {
      console.info("[recipient WS] close", e.code, e.reason);
      wsRef.current = null;
      // If a request was in-flight, surface the loss rather than spin forever.
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
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      switch (msg.type) {
        case "assistant_text_delta":
          setPartial((p) => p + msg.text);
          armThinkingTimer();
          break;
        case "assistant_text":
          clearThinkingTimer();
          setPartial("");
          setPending(false);
          setMessages((m) => [...m, { role: "bot", text: msg.text }]);
          break;
        case "sources":
          setSources(msg.items);
          break;
        case "error":
          clearThinkingTimer();
          setPartial("");
          setPending(false);
          setMessages((m) => [...m, { role: "bot", text: `(error) ${msg.message}` }]);
          break;
      }
    };
    wsRef.current = ws;
    return () => {
      if (thinkingTimerRef.current !== null) {
        window.clearTimeout(thinkingTimerRef.current);
      }
      // Disarm the close handler before closing — otherwise its async fire
      // (after StrictMode's cleanup-then-remount) would null out wsRef.current
      // which by then points to the NEW WebSocket from the remount.
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.close();
    };
  }, []);

  function send(text: string) {
    if (!text.trim() || pending) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("[recipient WS] send while not OPEN", ws?.readyState);
      setMessages((m) => [
        ...m,
        { role: "bot", text: "(not connected — refresh the page)" },
      ]);
      return;
    }
    setMessages((m) => [...m, { role: "you", text }]);
    setDraft("");
    setSources([]);
    setPartial("");
    setPending(true);
    stickToBottom();
    armThinkingTimer();
    ws.send(JSON.stringify({ type: "user_text", text }));
    // Re-focus so the user can keep typing while the agent responds.
    inputRef.current?.focus();
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full min-h-0">
      <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-slate-400 text-sm">
              Ask about feedback you have access to. I'll cite the source records.
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-xl px-3 py-2 ${
                m.role === "you"
                  ? "ml-auto bg-emerald-100 text-emerald-900 text-sm whitespace-pre-wrap"
                  : "bg-slate-100 text-slate-800"
              }`}
            >
              {m.role === "bot" ? <Markdown>{m.text}</Markdown> : m.text}
            </div>
          ))}
          {partial && (
            <div className="max-w-[85%] rounded-xl px-3 py-2 bg-slate-100 text-slate-800">
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
        <div className="border-t border-slate-200">
          {messages.length === 0 && (
            <div className="px-3 pt-3 flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => send(p)}
                  className="px-3 py-1.5 text-xs rounded-full border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100"
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          <div className="p-3 flex items-center gap-2">
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !pending) send(draft);
              }}
              placeholder="Ask a question…"
              className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm"
            />
            <button
              onClick={() => send(draft)}
              disabled={pending}
              className="px-3 py-2 bg-slate-800 text-white rounded text-sm disabled:opacity-50"
            >
              Send
            </button>
            <button
              onClick={() => send("Generate a report on the feedback I have access to in the last 90 days.")}
              disabled={pending}
              className="px-3 py-2 border border-slate-300 rounded text-sm text-slate-700 disabled:opacity-50"
            >
              Generate report
            </button>
          </div>
        </div>
      </div>
      <aside className="bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        <h3 className="text-xs uppercase font-medium text-slate-500 px-4 pt-4 pb-3 shrink-0">
          Sources ({sources.length})
        </h3>
        <div className="flex-1 min-h-0 overflow-y-auto px-4 pb-4">
          {sources.length === 0 && (
            <div className="text-slate-400 text-sm">
              Citations appear here after the bot answers.
            </div>
          )}
          <ul className="space-y-2 text-sm">
            {sources.map((s) => (
              <li key={s.id} className="border border-slate-200 rounded p-2">
                <div className="text-slate-800">{s.headline}</div>
                <div className="text-slate-500 text-xs mt-1">
                  about {s.subject ?? "—"} ·{" "}
                  {s.submitted_at ? new Date(s.submitted_at).toLocaleDateString() : "—"} ·{" "}
                  <span className="text-slate-400">{s.id.slice(0, 8)}…</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
