import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LocaleProvider, LOCALE_STORAGE_KEY, useLocale } from "./LocaleContext";
import type { LocaleCode } from "./locales";

// LocaleProvider is the only piece of state we persist between sessions,
// so the fallback behavior matters: a stale or malformed localStorage
// value must NOT make it into the live locale (it would crash tFor()
// on the next render because TABLES[unknown] is undefined).

function CurrentLocale() {
  const { locale } = useLocale();
  return <span data-testid="locale">{locale}</span>;
}

function SwitchTo({ target }: { target: LocaleCode }) {
  const { setLocale } = useLocale();
  // Effect ensures the setter runs once after mount, mirroring how
  // the real selector would fire from a click handler.
  useEffect(() => {
    setLocale(target);
  }, [setLocale, target]);
  return null;
}

describe("LocaleProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  // @testing-library/react v16 auto-registers cleanup when vitest globals
  // are enabled; we run with `globals: false` in vitest.config.ts so the
  // tests stay explicit about what they import — register it ourselves.
  afterEach(() => {
    cleanup();
  });

  it("falls back to en-US when localStorage is empty", () => {
    render(
      <LocaleProvider>
        <CurrentLocale />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("en-US");
  });

  it("uses a previously persisted valid locale", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "fr-CA");
    render(
      <LocaleProvider>
        <CurrentLocale />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("fr-CA");
  });

  it("falls back to en-US when the persisted code is unknown", () => {
    // Could happen after we drop a locale (e.g. removing pt-BR) or if
    // another tool wrote to the same key — must NOT propagate through.
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "ja-JP");
    render(
      <LocaleProvider>
        <CurrentLocale />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("en-US");
  });

  it("falls back to en-US when the persisted value is garbage", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "not-a-locale");
    render(
      <LocaleProvider>
        <CurrentLocale />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("en-US");
  });

  it("persists the chosen locale to localStorage", async () => {
    await act(async () => {
      render(
        <LocaleProvider>
          <CurrentLocale />
          <SwitchTo target="de-DE" />
        </LocaleProvider>,
      );
    });
    expect(screen.getByTestId("locale").textContent).toBe("de-DE");
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("de-DE");
  });

  it("survives a localStorage read failure", () => {
    // Simulate a browser denying access (private mode, quota errors).
    // The provider must not throw — it should fall back to en-US.
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage unavailable");
      },
    });
    try {
      render(
        <LocaleProvider>
          <CurrentLocale />
        </LocaleProvider>,
      );
      expect(screen.getByTestId("locale").textContent).toBe("en-US");
    } finally {
      // Restore so other tests aren't affected.
      if (original) Object.defineProperty(window, "localStorage", original);
    }
  });
});
