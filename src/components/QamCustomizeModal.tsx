import { type FC, useMemo } from "react";
import { ModalRoot, showModal } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useLayout } from "../customize/store";
import { useModules } from "../customize/modules";
import { getPresent, usePresentVersion } from "../customize/present";
import { useViews } from "../customize/viewStore";
import { useDesktopState } from "../desktop/useDesktop";
import { useDevice } from "../system/useDevice";
import { buildPanelQamCatalog } from "../qam/panelCatalog";
import { FocusRoot } from "./FocusRoot";
import { QamLayoutEditor } from "./QamLayoutEditor";
import { useCustomizeFocusVisibility } from "./useCustomizeFocusVisibility";

const QamCustomizeBody: FC = () => {
  const focusVisibilityRef = useCustomizeFocusVisibility();
  const { t } = useI18n();
  const layout = useLayout();
  const disabled = useModules();
  const desktopMode = !!useDesktopState().state?.enabled;
  const device = useDevice();
  const views = useViews();
  const presentVersion = usePresentVersion();
  const catalog = useMemo(() => buildPanelQamCatalog(views, {
    device, disabled, layout, desktopMode, present: getPresent,
  }), [views, device, disabled, layout, desktopMode, presentVersion]);

  return (
    <div ref={focusVisibilityRef} style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 640, width: "100%", margin: "0 auto" }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>
        {t("settings.qamShortcut")}
      </div>
      <QamLayoutEditor catalog={catalog} />
    </div>
  );
};

const QamCustomizeModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <QamCustomizeBody />
    </FocusRoot>
  </ModalRoot>
);

export function openQamCustomizeModal(): void {
  showModal(<QamCustomizeModal />, window);
}
