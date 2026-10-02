import type { CustomView } from "../../src/customize/views";
import { kioskPageViews } from "../../src/customize/kioskViews";

export interface KioskPage {
  id: string;
  name: string;
  blocks: readonly string[];
}

export const DEFAULT_KIOSK_BLOCKS = ["tdp", "autoTdp", "fanRpm", "temps", "battery", "night"] as const;

export function kioskPages(views: readonly CustomView[], chosen: readonly string[], defaultName: string): KioskPage[] {
  const shown = kioskPageViews(views, chosen);
  if (shown.length === 0) return [{ id: "default", name: defaultName, blocks: DEFAULT_KIOSK_BLOCKS }];
  return shown.map(({ id, name, blocks }) => ({ id, name, blocks }));
}
