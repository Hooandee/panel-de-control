import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { theme } from "../theme";
import { SectionView } from "../customize/blocks";
import { Loading } from "../components/Loading";
import { useMandos } from "../mandos/mandosContext";
import { MandosProviderMount } from "./providerMounts";

const MandosContent: FC = () => {
  const { config } = useMandos();
  if (!config) return <Loading />;
  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.section }}>
        <SectionView sectionId="mandos" />
      </div>
    </PanelSectionRow>
  );
};

export const MandosSection: FC = () => (
  <MandosProviderMount>
    <MandosContent />
  </MandosProviderMount>
);
