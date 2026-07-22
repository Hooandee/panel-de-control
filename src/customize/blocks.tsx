import { FC, useEffect, useMemo } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markBlockPresent } from "./present";

// Global block registry: maps a block id to a self-contained component that owns
// its own data and renders anywhere — a default section OR (later) a custom view.
// Shared state reaches a block either through a module singleton (read-only
// monitors: useDevice, useFanState) or a section context (controllers with writes/
// scope: Pantalla/Mandos/Potencia) — the latter must be rendered inside their
// section provider. Each section registers its blocks (registerBlock) at import.

export interface BlockDef {
  Component: FC;
  /** The section this block belongs to. Reserved for section-qualified registry
   *  keys / custom views; membership today is driven by the manifest. */
  sectionId: string;
  /**
   * Optional availability hook: whether this machine offers the block. Reads only
   * shared state (device info / a section's monitor or context) so probing it for a
   * hidden block adds no extra poll. Decoupled from rendering, so the editor still
   * lists a hidden block. Absent → always available. Called unconditionally once
   * per block by a stable probe, so it obeys the rules of hooks.
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

/** Render a registered block by id, or null if unknown (never throws). */
export const Block: FC<{ id: string }> = ({ id }) => {
  const def = REGISTRY[id];
  if (!def) return null;
  const C = def.Component;
  return <C />;
};

const alwaysAvailable = () => true;

/** Reports one block's availability to the present registry, without rendering it.
 *  Mounted for every block in a section (visible or hidden) so the editor knows
 *  which blocks a machine really has. `useAvailable` reads only shared state, so a
 *  hidden block's probe adds no extra poll. */
const Probe: FC<{ sectionId: string; id: string; useAvailable: () => boolean }> = ({
  sectionId,
  id,
  useAvailable,
}) => {
  const available = useAvailable();
  useEffect(() => {
    markBlockPresent(sectionId, id, available);
  }, [sectionId, id, available]);
  return null;
};

/**
 * Renders a section's blocks from the registry in the user's saved order, minus
 * hidden ones. Each block owns its data hook and self-gates (renders nothing when
 * its data is absent), so a sibling's poll tick no longer re-renders the whole
 * section. A hidden Probe per manifest block reports availability to the present
 * registry so the editor offers exactly the blocks that exist here — including
 * hidden ones, since availability is decoupled from rendering.
 */
export const SectionView: FC<{ sectionId: string }> = ({ sectionId }) => {
  const layout = useLayout();
  const ids = useMemo(() => blockOrder(sectionId), [sectionId]);
  const visible = useMemo(
    () => visibleIds(ids, layout.blocks[sectionId]),
    [ids, layout, sectionId],
  );
  return (
    <>
      {ids.map((id) => (
        <Probe key={`probe:${id}`} sectionId={sectionId} id={id} useAvailable={getBlockDef(id)?.useAvailable ?? alwaysAvailable} />
      ))}
      {visible.map((id) => (
        <Block key={id} id={id} />
      ))}
    </>
  );
};
