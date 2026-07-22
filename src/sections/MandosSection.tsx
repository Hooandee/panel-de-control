import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { theme } from "../theme";
import { useController } from "../mandos/useController";
import { MandosProvider } from "../mandos/mandosContext";
import { SectionView } from "../customize/blocks";
import { Loading } from "../components/Loading";

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
