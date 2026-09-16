import type { Lang } from "./languages";

// Generic Portuguese intentionally stays unmatched so pt-PT is never mistaken for pt-BR.
export function steamLangToLang(raw: string | null | undefined): Lang {
  const v = (raw ?? "").trim().toLowerCase();
  if (v === "en" || v.startsWith("english")) return "en";
  if (v === "it" || v.startsWith("italian")) return "it";
  if (v === "de" || v.startsWith("german")) return "de";
  if (v === "pt-br" || v === "brazilian" || v === "brazilian portuguese") return "pt-BR";
  return "es";
}
