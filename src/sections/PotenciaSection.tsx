import { FC } from "react";

import { Block, SectionView, BLOCK_GAP } from "../customize/blocks";
import { useDesktopState } from "../desktop/useDesktop";
import { desktopUiActive } from "../desktop/presentation";
import { PotenciaProviderMount } from "./providerMounts";

const PotenciaBody: FC = () => {
  const desktopMode = desktopUiActive(useDesktopState().state);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
      {desktopMode ? (
        <SectionView sectionId="power" desktopMode />
      ) : (
        <>
          <Block id="tdp" />
          <SectionView sectionId="power" />
        </>
      )}
    </div>
  );
};

export const PotenciaSection: FC = () => (
  <PotenciaProviderMount>
    <PotenciaBody />
  </PotenciaProviderMount>
);
