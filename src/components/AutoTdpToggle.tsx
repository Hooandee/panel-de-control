import { FC } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  checked: boolean;
  onChange: (enabled: boolean) => void;
}

/**
 * Auto‑TDP toggle, carried as its own reorderable/hideable Potencia block. Wears
 * an "experimental" badge — the dynamic loop is still being tuned. The toggle
 * lives here (not inside TdpSection) so it can sit after the GPU‑clock block.
 */
export const AutoTdpToggle: FC<Props> = ({ checked, onChange }) => {
  const { t } = useI18n();
  const label = (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {t("tdp.auto.title")}
      <span
        style={{
          fontSize: 10,
          padding: "1px 5px",
          borderRadius: 999,
          color: theme.color.warn,
          boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
        }}
      >
        {t("tdp.auto.experimental")}
      </span>
    </span>
  );
  return (
    <PanelSectionRow>
      <ToggleField
        label={label}
        description={t("tdp.auto.hint")}
        checked={checked}
        onChange={onChange}
        bottomSeparator="none"
      />
    </PanelSectionRow>
  );
};
