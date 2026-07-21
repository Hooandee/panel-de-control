import { FC, Fragment, ReactNode, useEffect, useMemo } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markPresent } from "./present";

/**
 * Renders a section's blocks in the user's saved order, skipping hidden ones.
 * `blocks` maps block id → node; a node may be false/null when its hardware is
 * absent (then it renders nothing, layered under the hide preference). Centralizes
 * the order+visibility loop so every section (System, Fans, …) shares it, and
 * reports which blocks actually exist on this machine (non-null) so the editor
 * only offers real blocks.
 */
export const SectionBlocks: FC<{ sectionId: string; blocks: Record<string, ReactNode> }> = ({ sectionId, blocks }) => {
  const layout = useLayout();
  // Order + visibility depend only on the section id and the saved layout, but
  // sections re-render on their own poll ticks (battery/cpu/fans) — memoize it.
  const ids = useMemo(
    () => visibleIds(blockOrder(sectionId), layout.blocks[sectionId]),
    [sectionId, layout],
  );
  // Blocks that actually exist here = manifest ids with a non-null node.
  const presentIds = blockOrder(sectionId).filter((id) => blocks[id] != null && blocks[id] !== false);
  const presentKey = presentIds.join(",");
  useEffect(() => {
    markPresent(sectionId, presentIds);
    // presentKey captures the set; presentIds identity changes every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, presentKey]);
  return (
    <>
      {ids.map((id) => (
        <Fragment key={id}>{blocks[id]}</Fragment>
      ))}
    </>
  );
};
