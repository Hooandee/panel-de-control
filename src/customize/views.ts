import { strArray } from "./layout";

export const VIEW_ICON_KEYS = [
  "star", "zap", "gamepad", "thermometer", "gauge", "grid", "monitor", "cpu", "sliders", "sparkles",
] as const;
export type ViewIconKey = (typeof VIEW_ICON_KEYS)[number];
export const DEFAULT_VIEW_ICON: ViewIconKey = "star";

export interface CustomView {
  id: string;
  name: string;
  icon: ViewIconKey;
  blocks: string[];
}

export const viewTabId = (id: string): string => `view:${id}`;
export const isViewTabId = (tabId: string): boolean => tabId.startsWith("view:");

export function providersFor(
  blockIds: string[],
  getSectionId: (id: string) => string | undefined,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of blockIds) {
    const s = getSectionId(id);
    if (s && !seen.has(s)) {
      seen.add(s);
      out.push(s);
    }
  }
  return out;
}

const asIcon = (v: unknown): ViewIconKey =>
  typeof v === "string" && (VIEW_ICON_KEYS as readonly string[]).includes(v)
    ? (v as ViewIconKey)
    : DEFAULT_VIEW_ICON;

// Corrupt/old-shape values must never throw downstream and brick the panel.
export function coerceViews(parsed: unknown): CustomView[] {
  if (!Array.isArray(parsed)) return [];
  const out: CustomView[] = [];
  for (const v of parsed) {
    if (!v || typeof v !== "object") continue;
    const o = v as { id?: unknown; name?: unknown; icon?: unknown; blocks?: unknown };
    if (typeof o.id !== "string" || !o.id) continue;
    out.push({
      id: o.id,
      name: typeof o.name === "string" ? o.name : "",
      icon: asIcon(o.icon),
      blocks: strArray(o.blocks),
    });
  }
  return out;
}
