import { FC, ReactNode, useMemo } from "react";

import { Block, getBlockDef } from "../customize/blocks";
import { providersFor } from "../customize/views";
import { useViews } from "../customize/viewStore";
import { theme } from "../theme";
import { SECTION_PROVIDERS } from "./providerMounts";

/** A user-composed tab: renders the view's blocks from the registry, wrapping them
 *  in the section providers their context blocks need. Blocks self-gate when absent
 *  on this device. */
export const CustomView: FC<{ viewId: string }> = ({ viewId }) => {
  const views = useViews();
  const view = views.find((v) => v.id === viewId);
  const blocks = view?.blocks ?? [];

  const sections = useMemo(
    () => providersFor(blocks, (id) => getBlockDef(id)?.sectionId),
    [blocks],
  );

  // Uniform spacing between blocks: they come from different sections with
  // heterogeneous internal margins, so a single gapped column normalizes the gaps.
  const content: ReactNode = (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section }}>
      {blocks.map((id) => (
        <Block key={id} id={id} />
      ))}
    </div>
  );

  return sections.reduceRight<ReactNode>((acc, s) => {
    const Mount = SECTION_PROVIDERS[s];
    return Mount ? <Mount>{acc}</Mount> : acc;
  }, content);
};
