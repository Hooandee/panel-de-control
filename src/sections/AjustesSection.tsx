import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { useI18n } from "../i18n";
import { LanguageToggle } from "../components/LanguageToggle";
import { theme } from "../theme";

/** Plugin settings. Today: language. Future home for units, theme, about, etc. */
export const AjustesSection: FC = () => {
  const { t } = useI18n();

  return (
    <PanelSectionRow>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: theme.space.sm,
        }}
      >
        <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>
          {t("settings.language")}
        </span>
        <LanguageToggle />
      </div>
    </PanelSectionRow>
  );
};
