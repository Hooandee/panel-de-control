import { FC, Fragment, ReactNode } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";

/**
 * Renders a section's blocks in the user's saved order, skipping hidden ones.
 * `blocks` maps block id → node; a node may be false/null when its hardware is
 * absent (then it renders nothing, layered under the hide preference). Centralizes
 * the order+visibility loop so every section (System, Fans, …) shares it.
 */
export const SectionBlocks: FC<{ sectionId: string; blocks: Record<string, ReactNode> }> = ({ sectionId, blocks }) => {
  const layout = useLayout();
  return (
    <>
      {visibleIds(blockOrder(sectionId), layout.blocks[sectionId]).map((id) => (
        <Fragment key={id}>{blocks[id]}</Fragment>
      ))}
    </>
  );
};
