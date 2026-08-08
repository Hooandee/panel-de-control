import type { Lang } from "./index";

// Steam's UI language name (e.g. "english", "italian") → plugin language.
// Unknown, null and blank values stay on es (the default).
export function steamLangToLang(raw: string | null | undefined): Lang {
  const v = (raw ?? "").trim().toLowerCase();
  if (v === "en" || v.startsWith("english")) return "en";
  if (v === "it" || v.startsWith("italian")) return "it";
  return "es";
}
