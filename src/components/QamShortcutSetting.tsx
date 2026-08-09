import { ButtonItem, Navigation, ToggleField } from "@decky/ui";
import { FC, useSyncExternalStore } from "react";

import { restartLoader } from "../api";
import { useI18n } from "../i18n";
import {
  getQamShortcutSnapshot,
  setQamShortcutEnabled,
  subscribeQamShortcut,
} from "../system/qamShortcut";
import { theme } from "../theme";

export const QamShortcutSetting: FC = () => {
  const { t } = useI18n();
  const state = useSyncExternalStore(
    subscribeQamShortcut,
    getQamShortcutSnapshot,
    getQamShortcutSnapshot,
  );
  const restartDecky = () => {
    Navigation.CloseSideMenus();
    window.setTimeout(() => { void restartLoader(); }, 500);
  };

  return (
    <>
      <ToggleField
        label={t("settings.qamShortcut")}
        description={t("settings.qamShortcut.desc")}
        checked={state.enabled}
        onChange={setQamShortcutEnabled}
        bottomSeparator="none"
      />
      {state.restartRequired && (
        <ButtonItem
          layout="below"
          description={t("settings.qamShortcut.restart")}
          onClick={restartDecky}
        >
          {t("settings.qamShortcut.restartButton")}
        </ButtonItem>
      )}
      {state.enabled && state.initialized && !state.registered && !state.restartRequired && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("settings.qamShortcut.fallback")}
        </div>
      )}
    </>
  );
};
