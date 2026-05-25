// Supported UI locales. The order is the order they appear in the
// language-selector dropdown. Each entry mirrors backend/app/locales.py;
// the `code` is what we send to the backend on every WS connection and
// message.
//
// `flag` is a regional-indicator unicode pair — used as a bleached
// background behind the two-letter label on the collapsed button, and
// next to the variant_label inside the popup list.

export type LocaleCode = "en-US" | "en-GB" | "es-ES" | "es-419" | "fr-FR" | "fr-CA" | "de-DE";

export type Locale = {
  code: LocaleCode;
  // Two-letter shorthand for the collapsed button. Same letters across
  // variants (EN/ES/FR/DE) — the flag does the disambiguation.
  short: string;
  // Localized name of the variant, e.g. "English (US)", "Español". Shown
  // in the popup list so a Spanish user can find their locale by reading
  // it in Spanish.
  label: string;
  // Country flag emoji used both as a background on the collapsed button
  // and next to the label in the popup.
  flag: string;
};

export const LOCALES: Locale[] = [
  { code: "en-US", short: "EN", label: "English (US)", flag: "🇺🇸" },
  { code: "en-GB", short: "EN", label: "English (UK)", flag: "🇬🇧" },
  { code: "es-ES", short: "ES", label: "Español (España)", flag: "🇪🇸" },
  { code: "es-419", short: "ES", label: "Español (Latinoamérica)", flag: "🇲🇽" },
  { code: "fr-FR", short: "FR", label: "Français (France)", flag: "🇫🇷" },
  { code: "fr-CA", short: "FR", label: "Français (Canada)", flag: "🇨🇦" },
  { code: "de-DE", short: "DE", label: "Deutsch", flag: "🇩🇪" },
];

export const DEFAULT_LOCALE: LocaleCode = "en-US";

const BY_CODE = Object.fromEntries(LOCALES.map((l) => [l.code, l])) as Record<LocaleCode, Locale>;

export function localeFromCode(code: string | null | undefined): Locale {
  if (code && code in BY_CODE) return BY_CODE[code as LocaleCode];
  return BY_CODE[DEFAULT_LOCALE];
}
