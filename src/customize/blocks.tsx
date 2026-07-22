import { FC, useEffect, useMemo } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markBlockPresent } from "./present";
import { theme } from "../theme";

/** Uniform vertical spacing between blocks — the container owns it so blocks stay
 *  margin-neutral and space evenly in a section or a custom view. */
export const BLOCK_GAP = theme.space.card;

export interface BlockDef {
  Component: FC;
  sectionId: string;
  useAvailable?: () => boolean;
}

const REGISTRY: Record<string, BlockDef> = {};

export function registerBlock(id: string, def: BlockDef): void {
  REGISTRY[id] = def;
}

export function getBlockDef(id: string): BlockDef | undefined {
  return REGISTRY[id];
}

export const Block: FC<{ id: string }> = ({ id }) => {
  const def = REGISTRY[id];
  if (!def) return null;
  const C = def.Component;
  return <C />;
};

const alwaysAvailable = () => true;

// Reports availability without rendering the block, so the editor lists a block
// even while it's hidden. useAvailable reads only shared state → no extra poll.
// `sectionKey` is the section id, or `view:<id>` for a custom view.
export const BlockProbe: FC<{ sectionKey: string; id: string }> = ({ sectionKey, id }) => {
  const available = (getBlockDef(id)?.useAvailable ?? alwaysAvailable)();
  useEffect(() => {
    markBlockPresent(sectionKey, id, available);
  }, [sectionKey, id, available]);
  return null;
};

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
        <BlockProbe key={`probe:${id}`} sectionKey={sectionId} id={id} />
      ))}
      <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
        {visible.map((id) => (
          <Block key={id} id={id} />
        ))}
      </div>
    </>
  );
};
