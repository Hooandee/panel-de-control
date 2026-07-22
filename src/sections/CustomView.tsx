import { FC, ReactNode, useMemo } from "react";

import { Block, BlockProbe, getBlockDef } from "../customize/blocks";
import { providersFor, viewTabId } from "../customize/views";
import { useViews } from "../customize/viewStore";
import { SECTION_PROVIDERS } from "./providerMounts";

/** A user-composed tab: renders the view's blocks from the registry, wrapping them
 *  in the section providers their context blocks need. Blocks self-gate when absent
 *  on this device; a probe reports presence under `view:<id>` so the shell can hide
 *  a view whose blocks are all unavailable. */
export const CustomView: FC<{ viewId: string }> = ({ viewId }) => {
  const views = useViews();
  const view = views.find((v) => v.id === viewId);
  const blocks = view?.blocks ?? [];
  const sectionKey = viewTabId(viewId);

  const sections = useMemo(
    () => providersFor(blocks, (id) => getBlockDef(id)?.sectionId),
    [blocks],
  );

  const content: ReactNode = (
    <>
      {blocks.map((id) => (
        <BlockProbe key={`probe:${id}`} sectionKey={sectionKey} id={id} />
      ))}
      {blocks.map((id) => (
        <Block key={id} id={id} />
      ))}
    </>
  );

  return sections.reduceRight<ReactNode>((acc, s) => {
    const Mount = SECTION_PROVIDERS[s];
    return Mount ? <Mount>{acc}</Mount> : acc;
  }, content);
};
