import type { Lang } from "./index";

// Steam reports names such as "english" and "italian"; unknown values keep the Spanish default.
export function steamLangToLang(raw: string | null | undefined): Lang {
  const v = (raw ?? "").trim().toLowerCase();
  if (v === "en" || v.startsWith("english")) return "en";
  if (v === "it" || v.startsWith("italian")) return "it";
  return "es";
}
