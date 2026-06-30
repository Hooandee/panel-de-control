import { FC, useEffect, useState } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { LanguageToggle } from "../components/LanguageToggle";
import { getTelemetryEnabled, setTelemetryEnabled } from "../api";
import { theme } from "../theme";

/** Plugin settings: language + usage-learning (telemetry) opt-out. */
export const AjustesSection: FC = () => {
  const { t } = useI18n();
  const [learn, setLearn] = useState<boolean | null>(null);

  useEffect(() => {
    getTelemetryEnabled().then(setLearn).catch(() => setLearn(true));
  }, []);

  const onToggle = (next: boolean) => {
    setLearn(next); // optimistic
    setTelemetryEnabled(next).catch(() => {});
  };

  return (
    <>
      <PanelSectionRow>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
          <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>
            {t("settings.language")}
          </span>
          <LanguageToggle />
        </div>
      </PanelSectionRow>

      {learn !== null && (
        <PanelSectionRow>
          <ToggleField
            label={t("settings.telemetry")}
            description={t("settings.telemetry.desc")}
            checked={learn}
            onChange={onToggle}
          />
        </PanelSectionRow>
      )}

      {learn === true && (
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("settings.telemetry.learning")}
          </div>
        </PanelSectionRow>
      )}
    </>
  );
};
