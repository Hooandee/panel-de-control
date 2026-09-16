import { FC } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { ExperimentalLabel } from "./ExperimentalBadge";

interface Props {
  checked: boolean;
  onChange: (enabled: boolean) => void;
}

export const AutoTdpToggle: FC<Props> = ({ checked, onChange }) => {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <ToggleField
        label={(
          <ExperimentalLabel
            badge={t("tdp.auto.experimental")}
            title={t("tdp.auto.title")}
          />
        )}
        description={t("tdp.auto.hint")}
        checked={checked}
        onChange={onChange}
        bottomSeparator="none"
      />
    </PanelSectionRow>
  );
};
