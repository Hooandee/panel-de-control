import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { theme } from "../theme";
import { SectionView } from "../customize/blocks";
import { MandosProviderMount } from "./providerMounts";

export const MandosSection: FC = () => (
  <MandosProviderMount>
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.section }}>
        <SectionView sectionId="mandos" />
      </div>
    </PanelSectionRow>
  </MandosProviderMount>
);
