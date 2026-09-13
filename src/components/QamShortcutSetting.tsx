import { ButtonItem } from "@decky/ui";
import { type FC, useSyncExternalStore } from "react";

import { useI18n } from "../i18n";
import { getQamRuntimeSnapshot, subscribeQamRuntime } from "../qam/runtime";
import { theme } from "../theme";
import { openCustomizeModal } from "./CustomizeModal";
import { reloadDeckyAfterClosingMenus } from "../system/reloadDecky";

export const QamShortcutSetting: FC = () => {
  const { t } = useI18n();
  const state = useSyncExternalStore(
    subscribeQamRuntime,
    getQamRuntimeSnapshot,
    getQamRuntimeSnapshot,
  );
  return (
    <>
      <ButtonItem
        layout="below"
        description={t("settings.qamShortcut.desc")}
        onClick={openCustomizeModal}
      >
        {t("settings.qamShortcut")}
      </ButtonItem>
      {state.restartRequired && (
        <ButtonItem
          layout="below"
          description={t("customize.qam.restart")}
          onClick={reloadDeckyAfterClosingMenus}
        >
          {t("customize.qam.restartButton")}
        </ButtonItem>
      )}
      {state.initialized
        && !state.applied
        && !state.restartRequired
        && state.reason !== "awaiting_render" && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("customize.qam.unavailable")}
        </div>
      )}
    </>
  );
};
