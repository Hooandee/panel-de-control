import { FC } from "react";
import { ToggleField, showModal } from "@decky/ui";
import { LuTriangleAlert } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  enabled: boolean;
  maxWatts: number;
  safeMaxWatts: number;
  failed?: boolean;
  onToggle: (enabled: boolean) => void;
}

export const ExperimentalTdpUnlock: FC<Props> = ({ enabled, maxWatts, safeMaxWatts, failed = false, onToggle }) => {
  const { t } = useI18n();
  const params = { max: maxWatts, safe: safeMaxWatts };
  return (
    <ToggleField
      label={t("settings.experimentalTdp")}
      description={t(
        failed
          ? "settings.experimentalTdp.applyFailed"
          : "settings.experimentalTdp.desc",
        params,
      )}
      checked={enabled}
      bottomSeparator="none"
      onChange={(next: boolean) => {
        if (!next) {
          onToggle(false);
          return;
        }
        showModal(
          <ConfirmDialog
            title={t("settings.experimentalTdp.confirm.title")}
            desc={t("settings.experimentalTdp.confirm.desc", params)}
            confirmLabel={t("settings.experimentalTdp.confirm.ok")}
            cancelLabel={t("settings.experimentalTdp.confirm.cancel")}
            icon={<LuTriangleAlert size={20} color={theme.color.warn} />}
            onConfirm={() => onToggle(true)}
          />,
        );
      }}
    />
  );
};
