import { FC, useEffect, useMemo } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markBlockPresent } from "./present";

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
