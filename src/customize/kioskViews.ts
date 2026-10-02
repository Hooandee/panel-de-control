import type { CustomView } from "./views";

export const KIOSK_VIEWS_KEY = "pdc:kioskViews";

export function coerceKioskViewIds(parsed: unknown): string[] {
  return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
}

/** Views shown as kiosk pages: the chosen ones in view order, or every view when none is chosen. */
export function kioskPageViews(views: readonly CustomView[], chosen: readonly string[]): CustomView[] {
  const withBlocks = views.filter((view) => view.blocks.length > 0);
  const picked = withBlocks.filter((view) => chosen.includes(view.id));
  return picked.length > 0 ? picked : withBlocks;
}

export function toggleKioskView(chosen: readonly string[], id: string): string[] {
  return chosen.includes(id) ? chosen.filter((other) => other !== id) : [...chosen, id];
}
