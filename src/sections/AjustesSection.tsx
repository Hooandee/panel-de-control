import { FC, useEffect, useState } from "react";
import { ButtonItem, PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { LanguageToggle } from "../components/LanguageToggle";
import { openCustomizeModal } from "../components/CustomizeModal";
import { getTelemetryEnabled, setTelemetryEnabled, getUnlockBatteryMax, setUnlockBatteryMax, getQamTdpBoost, setQamTdpBoost, resetTelemetry } from "../api";
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
  const [qamBoost, onToggleQamBoost] = useToggleSetting(getQamTdpBoost, setQamTdpBoost, false);

  // Destructive reset: a two-tap confirm avoids accidental wipes on the QAM.
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);
  const onReset = () => {
    setDone(false);
    if (!confirming) {
      setConfirming(true);
      return;
    }
    resetTelemetry()
      .then(() => { setConfirming(false); setDone(true); })
      .catch(() => setConfirming(false));
  };
  const resetLabel = done
    ? t("settings.reset.done")
    : confirming
      ? t("settings.reset.confirm")
      : t("settings.reset");

  return (
    // One row holding a spaced column so the settings don't glue together. Null
    // children (not-yet-loaded toggles) collapse their slot — no double gaps.
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.section }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
          <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>
            {t("settings.language")}
          </span>
          <LanguageToggle />
        </div>

        {learn !== null && (
          <ToggleField
            label={t("settings.telemetry")}
            description={t("settings.telemetry.desc")}
            checked={learn}
            onChange={onToggle}
          />
        )}

        {learn === true && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("settings.telemetry.learning")}
          </div>
        )}

        {battMax !== null && (
          <ToggleField
            label={t("settings.battmax")}
            description={t("settings.battmax.desc")}
            checked={battMax}
            onChange={onToggleBattMax}
          />
        )}

        {qamBoost !== null && (
          <ToggleField
            label={t("settings.qamboost")}
            description={t("settings.qamboost.desc")}
            checked={qamBoost}
            onChange={onToggleQamBoost}
          />
        )}

        {/* Open the full-screen tab + block layout editor. */}
        <ButtonItem layout="below" description={t("customize.button.desc")} onClick={() => openCustomizeModal()}>
          {t("customize.button")}
        </ButtonItem>

        {/* Start-from-scratch: wipe all learned telemetry (TDP + fans). Two-tap
            confirm. Doesn't touch manual profiles/curves. */}
        <ButtonItem layout="below" description={t("settings.reset.desc")} onClick={onReset}>
          {resetLabel}
        </ButtonItem>
      </div>
    </PanelSectionRow>
  );
};
