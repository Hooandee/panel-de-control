import { FC } from "react";

import { Block, SectionView, BLOCK_GAP } from "../customize/blocks";
import { usePotencia } from "../tdp/potenciaContext";
import { useDesktopState } from "../desktop/useDesktop";
import { PotenciaProviderMount } from "./providerMounts";

const PotenciaBody: FC = () => {
  const { monitorOnly } = usePotencia();
  const desktopMode = !!useDesktopState().state?.enabled;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
      {desktopMode ? (
        <SectionView sectionId="power" desktopMode />
      ) : (
        <>
          <Block id="tdp" />
          {!monitorOnly && <SectionView sectionId="power" />}
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
