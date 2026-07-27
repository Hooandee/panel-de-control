import type { Lang } from "./index";

// Steam's UI language name (e.g. "english", "spanish") → plugin language.
// English → en; everything else, and null/blank/unknown → es (the default).
export function steamLangToLang(raw: string | null | undefined): Lang {
  const v = (raw ?? "").trim().toLowerCase();
  if (v === "en" || v.startsWith("english")) return "en";
  return "es";
}
