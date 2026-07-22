import { FC } from "react";

import { Block, SectionView } from "../customize/blocks";
import { usePotencia } from "../tdp/potenciaContext";
import { PotenciaProviderMount } from "./providerMounts";

const PotenciaBody: FC = () => {
  const { monitorOnly } = usePotencia();
  return (
    <>
      <Block id="tdp" />
      {!monitorOnly && <SectionView sectionId="power" />}
    </>
  );
};

export const PotenciaSection: FC = () => (
  <PotenciaProviderMount>
    <PotenciaBody />
  </PotenciaProviderMount>
);
