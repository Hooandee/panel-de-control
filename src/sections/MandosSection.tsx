import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { theme } from "../theme";
import { useController } from "../mandos/useController";
import { MandosProvider } from "../mandos/mandosContext";
import { SectionView } from "../customize/blocks";
import { Loading } from "../components/Loading";
import "./mandosBlocks"; // registers the Mandos blocks

/**
 * Mandos — controller manager hub.
 *
 * Cooperates with whichever daemon owns the gamepad (Handheld Daemon on Bazzite,
 * InputPlumber on SteamOS) — we never grab evdev ourselves. On InputPlumber we
 * offer a real per-button remap editor; on HHD we expose its controller settings.
 * The manager status, remap editor and settings are self-contained blocks sharing
 * one controller config via MandosProvider.
 */
export const MandosSection: FC = () => {
  const controller = useController();
  if (!controller.config) return <Loading />;
  return (
    <MandosProvider value={controller}>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.section }}>
          <SectionView sectionId="mandos" />
        </div>
      </PanelSectionRow>
    </MandosProvider>
  );
};
