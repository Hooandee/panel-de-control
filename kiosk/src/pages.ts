import type { CustomView } from "../../src/customize/views";

export interface KioskPage {
  id: string;
  name: string;
  blocks: readonly string[];
}

export const DEFAULT_KIOSK_BLOCKS = ["tdp", "autoTdp", "fanRpm", "temps", "battery", "night"] as const;

export function kioskPages(views: readonly CustomView[], defaultName: string): KioskPage[] {
  const withBlocks = views.filter((view) => view.blocks.length > 0);
  if (withBlocks.length === 0) return [{ id: "default", name: defaultName, blocks: DEFAULT_KIOSK_BLOCKS }];
  return withBlocks.map(({ id, name, blocks }) => ({ id, name, blocks }));
}
