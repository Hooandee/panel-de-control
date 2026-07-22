import { FC } from "react";

import { SectionView } from "../customize/blocks";
import "./systemBlocks"; // registers the Sistema blocks

/** System controls: battery + CPU (collapsible, rich) then brightness + volume
 *  (simple bars), plus eco mode and the RGB card — each a self-contained block
 *  rendered from the registry in the user's saved order. */
export const SistemaSection: FC = () => <SectionView sectionId="system" />;
