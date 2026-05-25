import { useEffect, useRef, useState } from "react";
import { useLocale } from "../i18n/LocaleContext";
import { Locale, LOCALES, localeFromCode } from "../i18n/locales";

// Collapsed button: two-letter language code and the country flag side
// by side. (Earlier prototype used a bleached flag behind the letters,
// but the emoji-as-background read as muddy noise — legibility wins.)
export function LocaleSelector() {
  const { locale, setLocale, t } = useLocale();
  const current = localeFromCode(locale);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Click-outside / Escape both close the popup. The first happens once
  // (so we don't fight with the trigger click), the second is a
  // standard accessibility expectation for menus.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function pick(loc: Locale) {
    setLocale(loc.code);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={t("locale.aria_label")}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={current.label}
        className="inline-flex items-center gap-1.5 h-7 px-2 rounded border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300"
      >
        <span>{current.short}</span>
        <span aria-hidden className="text-base leading-none">
          {current.flag}
        </span>
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label={t("locale.aria_label")}
          className="absolute right-0 mt-1 w-56 max-h-72 overflow-y-auto rounded border border-slate-200 bg-white shadow-lg z-50"
        >
          {LOCALES.map((loc) => {
            const selected = loc.code === locale;
            return (
              <li key={loc.code}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => pick(loc)}
                  className={`w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-slate-50 ${
                    selected ? "bg-slate-100 text-slate-900" : "text-slate-700"
                  }`}
                >
                  <span className="text-lg leading-none">{loc.flag}</span>
                  <span className="flex-1">{loc.label}</span>
                  {selected && <span aria-hidden>✓</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
