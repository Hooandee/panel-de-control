import { FC } from "react";

import {
  Block,
  SectionView,
  BLOCK_GAP,
  useSectionBlockIds,
} from "../customize/blocks";
import { useDesktopState } from "../desktop/useDesktop";
import { desktopUiActive } from "../desktop/presentation";
import { PotenciaProviderMount } from "./providerMounts";

const PotenciaBody: FC<{ desktopMode: boolean }> = ({ desktopMode }) => (
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

export const PotenciaSection: FC = () => {
  const desktopMode = desktopUiActive(useDesktopState().state);
  const { visible: visibleBlocks } = useSectionBlockIds("power", desktopMode);
  const showProfileSelector = !desktopMode || visibleBlocks.includes("steamPerformance");
  return (
    <PotenciaProviderMount showProfileSelector={showProfileSelector}>
      <PotenciaBody desktopMode={desktopMode} />
    </PotenciaProviderMount>
  );
};
