import { FC } from "react";

import { SectionView } from "../customize/blocks";

/** Live monitor (RPM/temps) + fan-curve control, each a self-contained block
 *  rendered from the registry in the user's saved order. */
export const VentiladoresSection: FC = () => <SectionView sectionId="fans" />;
