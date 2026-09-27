import { PanelSectionRow } from "@decky/ui";

import ambientPreview from "../assets/ambient-preview.jpg";
import { ComingSoonCard } from "../components/ComingSoonCard";
import { theme } from "../theme";

export function AmbienteSection() {
  return (
    <PanelSectionRow>
      <div style={{ marginTop: theme.space.sm }}>
        <ComingSoonCard image={ambientPreview} keyPrefix="ambient.soon" />
      </div>
    </PanelSectionRow>
  );
}
