import { FC, Fragment, useEffect, useMemo } from "react";

import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markBlockPresent } from "./present";
import { getBlockDef } from "./blockRegistry";

// Renderers for the global block registry. The registry state lives in
// blockRegistry.ts; here we render blocks by id, in a section or a custom view.
export type { BlockDef } from "./blockRegistry";
export { registerBlock, getBlockDef } from "./blockRegistry";

/** Render a registered block by id, or null if unknown (never throws). */
export const Block: FC<{ id: string }> = ({ id }) => {
  const def = getBlockDef(id);
  if (!def) return null;
  const C = def.Component;
  return <C />;
};

const alwaysAvailable = () => true;

/** Reports one block's availability to the present registry, without rendering it.
 *  Mounted for every block in a section (visible or hidden) so the editor knows
 *  which blocks a machine really has. `useAvailable` reads only shared singletons,
 *  so a hidden block's probe adds no extra poll. */
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
        <Fragment key={id}>
          <Block id={id} />
        </Fragment>
      ))}
    </>
  );
};
