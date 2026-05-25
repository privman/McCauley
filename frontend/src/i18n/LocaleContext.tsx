import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { DEFAULT_LOCALE, LocaleCode, localeFromCode } from "./locales";
import { StringKey, tFor } from "./strings";

// Persisted across reloads so a returning user lands in their chosen
// language immediately, before any backend round-trip.
export const LOCALE_STORAGE_KEY = "mccauley.locale";

type LocaleContextValue = {
  locale: LocaleCode;
  setLocale: (next: LocaleCode) => void;
  t: (key: StringKey) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readPersisted(): LocaleCode {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    // Canonicalize against the known locale list — a stale value (left
    // by an older build with a different code set, or random garbage
    // from another app sharing the storage key) must fall back to the
    // default rather than be cast through as-is. The previous
    // implementation cast directly to LocaleCode, which then crashed
    // tFor() on the first render because TABLES[unknown] is undefined.
    return localeFromCode(raw).code;
  } catch {
    return DEFAULT_LOCALE;
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(() => readPersisted());

  useEffect(() => {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      // localStorage can be disabled (e.g. private mode in some browsers);
      // fall back to in-memory state silently.
    }
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: LocaleCode) => {
    setLocaleState(next);
  }, []);

  const t = useCallback((key: StringKey) => tFor(locale, key), [locale]);

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>{children}</LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (ctx === null) {
    throw new Error("useLocale must be used inside <LocaleProvider>");
  }
  return ctx;
}
