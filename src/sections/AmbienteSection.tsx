import { PanelSectionRow } from "@decky/ui";

import ambientPreview from "../assets/ambient-preview.jpg";
import { ComingSoonCard } from "../components/ComingSoonCard";
import { useI18n } from "../i18n";
import { theme } from "../theme";

export function AmbienteSection() {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <div style={{ marginTop: theme.space.sm }}>
        <ComingSoonCard
          image={ambientPreview}
          imageAlt={t("ambient.soon.imageAlt")}
          title={t("ambient.soon.title")}
          body={t("ambient.soon.body")}
        />
      </div>
    </PanelSectionRow>
  );
}
