import { FC, useEffect } from "react";

import { markBlockPresent } from "./present";

// Global block registry: maps a block id to a self-contained component that owns
// its own data (hooks) and renders anywhere — a default section OR a custom view.
// Each section registers its blocks (registerBlock) at import; the registry is the
// single source both the shell and custom views render from.

export interface BlockDef {
  sectionId: string;
  Component: FC;
}

const REGISTRY: Record<string, BlockDef> = {};

/** Register a block component under its id. Idempotent (last wins). */
export function registerBlock(id: string, def: BlockDef): void {
  REGISTRY[id] = def;
}

export function getBlockDef(id: string): BlockDef | undefined {
  return REGISTRY[id];
}

/** Render a registered block by id, or null if unknown (never throws). */
export const Block: FC<{ id: string }> = ({ id }) => {
  const def = REGISTRY[id];
  if (!def) return null;
  const C = def.Component;
  return <C />;
};

/** A standalone block calls this to report whether it has content on this machine,
 *  so the editor and custom views only offer blocks that actually exist here. Call
 *  it unconditionally (before any early return) to respect the rules of hooks. */
export function useBlockPresence(sectionId: string, id: string, present: boolean): void {
  useEffect(() => {
    markBlockPresent(sectionId, id, present);
  }, [sectionId, id, present]);
}
