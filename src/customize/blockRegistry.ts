import type { FC } from "react";

// Pure block registry (no React/JSX, no @decky) — the renderers (<Block/>,
// <SectionView/>) live in blocks.tsx and read this shared state. Maps a block id
// to a self-contained component that owns its own data (hooks) and renders
// anywhere — a default section OR a custom view.

export interface BlockDef {
  sectionId: string;
  Component: FC;
  /**
   * Optional availability hook: whether this machine offers the block. Reads only
   * SHARED singletons (device info, a section's ref-counted monitor) so probing it
   * for a hidden block adds no extra poll. Decoupled from rendering, so the editor
   * still lists a hidden block. Absent → always available. Called unconditionally
   * once per block by a stable probe, so it obeys the rules of hooks.
   */
  useAvailable?: () => boolean;
}

const REGISTRY: Record<string, BlockDef> = {};

/** Register a block component under its id. Idempotent (last wins). */
export function registerBlock(id: string, def: BlockDef): void {
  REGISTRY[id] = def;
}

export function getBlockDef(id: string): BlockDef | undefined {
  return REGISTRY[id];
}
