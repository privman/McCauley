import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api";
import { Markdown } from "../components/Markdown";
import { useAutoScroll } from "../components/useAutoScroll";
import { useLocale } from "../i18n/LocaleContext";
import type { StringKey } from "../i18n/strings";

type Msg = { role: "you" | "bot"; text: string };
type SBI = {
  idx: number;
  situation: string | null;
  behavior: string | null;
  impact: string | null;
};
type Source = {
  id: string;
  headline: string;
  subject: string | null;
  subject_kind: "user" | "unit" | null;
  sentiment: "positive" | "constructive" | "negative" | "mixed" | null;
  topic_tags: string[];
  provider: string | null;
  is_anonymous: boolean;
  submitted_at: string | null;
  sbis: SBI[];
};

const EXAMPLE_PROMPT_KEYS: StringKey[] = [
  "my.example_prompt_1",
  "my.example_prompt_2",
  "my.example_prompt_3",
  "my.example_prompt_4",
];

const THINKING_DELAY_MS = 750;

export default function MyFeedback() {
  const { locale, t } = useLocale();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [partial, setPartial] = useState("");
  const [pending, setPending] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const thinkingTimerRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Same trick as GiveFeedback — keep the latest locale reachable from
  // callbacks defined in the connect effect.
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
    const ws = new WebSocket(wsUrl("/ws/recipient", { locale: localeRef.current }));
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
          setMessages((m) => [...m, { role: "bot", text: t("give.connection_lost") }]);
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
          setSelectedSourceId(null);
          break;
        case "error":
          clearThinkingTimer();
          setPartial("");
          setPending(false);
          setMessages((m) => [
            ...m,
            { role: "bot", text: `${t("give.error_prefix")} ${msg.message}` },
          ]);
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
    // The WS handlers reference `t` from the initial locale; that's
    // intentional — adding `t` would force a reconnect on every locale
    // flip, and the only `t` use here is for the rare connection-lost /
    // error frames, which the user can recover from with a refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function send(text: string) {
    if (!text.trim() || pending) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("[recipient WS] send while not OPEN", ws?.readyState);
      setMessages((m) => [...m, { role: "bot", text: t("give.not_connected") }]);
      return;
    }
    setMessages((m) => [...m, { role: "you", text }]);
    setDraft("");
    setSources([]);
    setSelectedSourceId(null);
    setPartial("");
    setPending(true);
    stickToBottom();
    ws.send(JSON.stringify({ type: "user_text", text, locale }));
    // Re-focus so the user can keep typing while the agent responds.
    inputRef.current?.focus();
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full min-h-0">
      <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-slate-400 text-sm">{t("my.empty_hint")}</div>
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
              {t("give.thinking")}
            </div>
          )}
        </div>
        <div className="border-t border-slate-200">
          {messages.length === 0 && (
            <div className="px-3 pt-3 flex flex-wrap gap-2">
              {EXAMPLE_PROMPT_KEYS.map((key) => {
                const prompt = t(key);
                return (
                  <button
                    key={key}
                    onClick={() => send(prompt)}
                    className="px-3 py-1.5 text-xs rounded-full border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100"
                  >
                    {prompt}
                  </button>
                );
              })}
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
              placeholder={t("my.placeholder")}
              className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm"
            />
            <button
              onClick={() => send(draft)}
              disabled={pending}
              className="px-3 py-2 bg-slate-800 text-white rounded text-sm disabled:opacity-50"
            >
              {t("my.send")}
            </button>
            <button
              onClick={() => send(t("my.generate_report_message"))}
              disabled={pending}
              className="px-3 py-2 border border-slate-300 rounded text-sm text-slate-700 disabled:opacity-50"
            >
              {t("my.generate_report")}
            </button>
          </div>
        </div>
      </div>
      <aside className="bg-white border border-slate-200 rounded-xl flex flex-col min-h-0 overflow-hidden">
        {selectedSourceId === null ? (
          <SourceList sources={sources} onSelect={(id) => setSelectedSourceId(id)} />
        ) : (
          <SourceDetail
            source={sources.find((s) => s.id === selectedSourceId) ?? null}
            onBack={() => setSelectedSourceId(null)}
          />
        )}
      </aside>
    </div>
  );
}

function SourceList({ sources, onSelect }: { sources: Source[]; onSelect: (id: string) => void }) {
  const { locale, t } = useLocale();
  return (
    <>
      <h3 className="text-xs uppercase font-medium text-slate-500 px-4 pt-4 pb-3 shrink-0">
        {t("my.sources_heading")} ({sources.length})
      </h3>
      <div className="flex-1 min-h-0 overflow-y-auto px-4 pb-4">
        {sources.length === 0 && (
          <div className="text-slate-400 text-sm">{t("my.sources_empty")}</div>
        )}
        <ul className="space-y-2 text-sm">
          {sources.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                className="w-full text-left border border-slate-200 rounded p-2 hover:bg-slate-50 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-300"
              >
                <div className="text-slate-800">{s.headline}</div>
                <div className="text-slate-500 text-xs mt-1">
                  {t("my.source_about")} {s.subject ?? t("my.source_dash")} ·{" "}
                  {s.submitted_at
                    ? new Date(s.submitted_at).toLocaleDateString(locale)
                    : t("my.source_dash")}{" "}
                  · <span className="text-slate-400">{s.id.slice(0, 8)}…</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

const SENTIMENT_STYLES: Record<string, string> = {
  positive: "bg-emerald-100 text-emerald-800",
  constructive: "bg-amber-100 text-amber-800",
  negative: "bg-rose-100 text-rose-800",
  mixed: "bg-slate-100 text-slate-700",
};

function SourceDetail({ source, onBack }: { source: Source | null; onBack: () => void }) {
  const { locale, t } = useLocale();
  if (!source) {
    // Source vanished (new query cleared the list). Bounce back.
    return (
      <div className="p-4 text-sm text-slate-500">
        <button onClick={onBack} className="text-slate-600 hover:text-slate-900 text-xs">
          {t("my.source_back")}
        </button>
        <div className="mt-3">{t("my.source_gone")}</div>
      </div>
    );
  }
  const dash = t("my.source_dash");
  return (
    <>
      <div className="flex items-center gap-2 px-4 pt-4 pb-3 shrink-0 border-b border-slate-200">
        <button
          onClick={onBack}
          className="text-slate-600 hover:text-slate-900 text-xs flex items-center gap-1"
        >
          {t("my.source_back")}
        </button>
        <span className="text-xs uppercase font-medium text-slate-500 ml-auto">
          {t("my.source_heading")}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 text-sm space-y-3">
        <div>
          <div className="text-slate-800 font-medium">{source.headline}</div>
          <div className="text-slate-500 text-xs mt-1">
            {t("my.source_about")} {source.subject ?? dash}
            {source.subject_kind ? ` (${source.subject_kind})` : ""}
          </div>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          <dt className="text-slate-500">{t("my.source_from")}</dt>
          <dd className="text-slate-700">
            {source.is_anonymous ? t("my.source_anonymous") : (source.provider ?? dash)}
          </dd>
          <dt className="text-slate-500">{t("my.source_submitted")}</dt>
          <dd className="text-slate-700">
            {source.submitted_at ? new Date(source.submitted_at).toLocaleDateString(locale) : dash}
          </dd>
          <dt className="text-slate-500">{t("my.source_id")}</dt>
          <dd className="text-slate-400 font-mono">{source.id.slice(0, 8)}…</dd>
        </dl>
        {(source.sentiment || source.topic_tags.length > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {source.sentiment && (
              <span
                className={`px-2 py-0.5 rounded text-xs ${
                  SENTIMENT_STYLES[source.sentiment] ?? "bg-slate-100 text-slate-700"
                }`}
              >
                {source.sentiment}
              </span>
            )}
            {source.topic_tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700">
                {tag}
              </span>
            ))}
          </div>
        )}
        <div className="space-y-3">
          <div className="text-xs uppercase font-medium text-slate-500">
            {t("my.source_examples")}
          </div>
          {source.sbis.length === 0 && (
            <div className="text-slate-400">{t("my.source_examples_empty")}</div>
          )}
          {source.sbis.map((s) => (
            <div key={s.idx} className="border border-slate-200 rounded p-2 space-y-1.5">
              <div className="font-medium text-slate-500 text-xs">#{s.idx + 1}</div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                <dt className="text-slate-500">S</dt>
                <dd className="text-slate-800 whitespace-pre-wrap break-words">
                  {s.situation ?? dash}
                </dd>
                <dt className="text-slate-500">B</dt>
                <dd className="text-slate-800 whitespace-pre-wrap break-words">
                  {s.behavior ?? dash}
                </dd>
                <dt className="text-slate-500">I</dt>
                <dd className="text-slate-800 whitespace-pre-wrap break-words">
                  {s.impact ?? dash}
                </dd>
              </dl>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
