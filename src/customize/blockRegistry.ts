import type { FC } from "react";
import type { DeviceInfo } from "../api";

// Pure block registry (no React/JSX, no @decky) so its availability logic stays
// unit-testable. The renderers (<Block/>, <SectionView/>) live in blocks.tsx and
// read this shared state. Maps a block id to a self-contained component that owns
// its own data (hooks) and renders anywhere — a default section OR a custom view.

/** Shared, poll-free signals a block's availability predicate reads. */
export interface Caps {
  device: DeviceInfo | null;
}

export interface BlockDef {
  sectionId: string;
  Component: FC;
  /**
   * Whether this machine can offer the block, from shared device/caps only — no
   * poll, no mount. Decoupled from rendering so the editor knows a hidden block
   * still exists (and can be un-hidden). Defaults to always-available; a block's
   * live/loading state is handled inside its Component, not here.
   */
  available?: (caps: Caps) => boolean;
}

const REGISTRY: Record<string, BlockDef> = {};

/** Register a block component under its id. Idempotent (last wins). */
export function registerBlock(id: string, def: BlockDef): void {
  REGISTRY[id] = def;
}

export function getBlockDef(id: string): BlockDef | undefined {
  return REGISTRY[id];
}

/** Pure: the subset of `ids` whose registered block is available under `caps`.
 *  Unknown ids and blocks without a predicate are treated as available. */
export function availableIds(ids: string[], caps: Caps): string[] {
  return ids.filter((id) => {
    const a = REGISTRY[id]?.available;
    return a ? a(caps) : true;
  });
}
