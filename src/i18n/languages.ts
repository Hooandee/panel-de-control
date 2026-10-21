export const LANGUAGE_OPTIONS = [
  { data: "es", label: "Español" },
  { data: "en", label: "English" },
  { data: "it", label: "Italiano" },
  { data: "de", label: "Deutsch" },
  { data: "pt-BR", label: "Português (Brasil)" },
  { data: "fr", label: "Français" },
] as const;

export type Lang = (typeof LANGUAGE_OPTIONS)[number]["data"];

export const SUPPORTED_LANGUAGES: readonly Lang[] = LANGUAGE_OPTIONS.map(({ data }) => data);
