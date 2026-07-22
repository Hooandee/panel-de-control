import { FC, Fragment, useEffect, useMemo } from "react";

import { useDevice } from "../system/useDevice";
import { useLayout } from "./store";
import { visibleIds } from "./layout";
import { blockOrder } from "./manifest";
import { markPresent } from "./present";
import { availableIds, getBlockDef } from "./blockRegistry";

// Renderers for the global block registry. The registry state + its pure
// availability logic live in blockRegistry.ts; here we render blocks by id, in a
// section or a custom view.
export type { Caps, BlockDef } from "./blockRegistry";
export { registerBlock, getBlockDef, availableIds } from "./blockRegistry";

/** Render a registered block by id, or null if unknown (never throws). */
export const Block: FC<{ id: string }> = ({ id }) => {
  const def = getBlockDef(id);
  if (!def) return null;
  const C = def.Component;
  return <C />;
};

/**
 * Renders a section's blocks from the registry in the user's saved order, showing
 * only those the device has (available) and the user hasn't hidden. Reports the
 * available set to the present registry so the editor offers exactly the blocks
 * that exist here — including hidden ones, since availability is decoupled from
 * rendering. Each block owns its own data hook, so a sibling's poll tick no longer
 * re-renders the whole section.
 */
export const SectionView: FC<{ sectionId: string }> = ({ sectionId }) => {
  const layout = useLayout();
  const device = useDevice();
  const ids = useMemo(() => blockOrder(sectionId), [sectionId]); // static per section
  const caps = useMemo(() => ({ device }), [device]);

  const present = useMemo(() => availableIds(ids, caps), [ids, caps]);
  const presentKey = present.join(",");
  useEffect(() => {
    markPresent(sectionId, present);
    // presentKey captures the set; `present` identity changes every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, presentKey]);

  const visible = useMemo(
    () => visibleIds(ids, layout.blocks[sectionId]).filter((id) => present.includes(id)),
    [ids, layout, sectionId, present],
  );

  return (
    <>
      {visible.map((id) => (
        <Fragment key={id}>
          <Block id={id} />
        </Fragment>
      ))}
    </>
  );
};
