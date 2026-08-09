import {
  ButtonItem,
  Navigation,
  PanelSection,
  PanelSectionRow,
  QuickAccessTab,
} from "@decky/ui";
import { FC, PropsWithChildren, useState } from "react";

import { PDC_QAM_TAB_ID } from "../deckyInternal";
import { useI18n } from "../i18n";
import { QamPanelGate } from "./QamPanelGate";

interface QamShortcutDeckyEntryProps extends PropsWithChildren {
  lifecycle: AbortController;
  fallbackLifecycle: AbortSignal;
}

export const QamShortcutDeckyEntry: FC<QamShortcutDeckyEntryProps> = ({
  children,
  fallbackLifecycle,
  lifecycle,
}) => {
  const { t } = useI18n();
  const [usingFallback, setUsingFallback] = useState(lifecycle.signal.aborted);

  if (usingFallback) {
    return <QamPanelGate lifecycle={fallbackLifecycle}>{children}</QamPanelGate>;
  }

  return (
    <PanelSection>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          description={t("settings.qamShortcut.deckyEntry.desc")}
          onClick={() => Navigation.OpenQuickAccessMenu(PDC_QAM_TAB_ID as QuickAccessTab)}
        >
          {t("settings.qamShortcut.deckyEntry")}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          description={t("settings.qamShortcut.deckyFallback.desc")}
          onClick={() => {
            lifecycle.abort();
            setUsingFallback(true);
          }}
        >
          {t("settings.qamShortcut.deckyFallback")}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};
