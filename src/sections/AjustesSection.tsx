import { FC, useEffect, useState } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { LanguageToggle } from "../components/LanguageToggle";
import { getTelemetryEnabled, setTelemetryEnabled, getUnlockBatteryMax, setUnlockBatteryMax } from "../api";
import { theme } from "../theme";

/** A persisted boolean setting: fetch on mount, optimistic update on toggle.
 *  Returns null until the first read lands (so the UI can hide the control). */
function useToggleSetting(
  getter: () => Promise<boolean>,
  setter: (v: boolean) => Promise<unknown>,
  fallback: boolean,
): [boolean | null, (next: boolean) => void] {
  const [value, setValue] = useState<boolean | null>(null);
  useEffect(() => {
    getter().then(setValue).catch(() => setValue(fallback));
  }, []);
  const onToggle = (next: boolean) => {
    setValue(next); // optimistic
    setter(next).catch(() => {});
  };
  return [value, onToggle];
}

/** Plugin settings: language + usage-learning opt-out + battery-max unlock. */
export const AjustesSection: FC = () => {
  const { t } = useI18n();
  const [learn, onToggle] = useToggleSetting(getTelemetryEnabled, setTelemetryEnabled, true);
  const [battMax, onToggleBattMax] = useToggleSetting(getUnlockBatteryMax, setUnlockBatteryMax, false);

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

      {battMax !== null && (
        <PanelSectionRow>
          <ToggleField
            label={t("settings.battmax")}
            description={t("settings.battmax.desc")}
            checked={battMax}
            onChange={onToggleBattMax}
          />
        </PanelSectionRow>
      )}
    </>
  );
};
