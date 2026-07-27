import { FC } from "react";

import { Block, SectionView, BLOCK_GAP } from "../customize/blocks";
import { usePotencia } from "../tdp/potenciaContext";
import { PotenciaProviderMount } from "./providerMounts";

const PotenciaBody: FC = () => {
  const { monitorOnly } = usePotencia();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
      <Block id="tdp" />
      {!monitorOnly && <SectionView sectionId="power" />}
    </div>
  );
};

export const PotenciaSection: FC = () => (
  <PotenciaProviderMount>
    <PotenciaBody />
  </PotenciaProviderMount>
);
