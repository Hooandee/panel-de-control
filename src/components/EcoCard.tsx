import { FC, ReactNode } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { LuLeaf, LuMonitorOff, LuRocket, LuZap } from "react-icons/lu";

import { EcoState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  state: EcoState;
  onToggle: (enabled: boolean) => void;
}

const Effect: FC<{ icon: ReactNode; label: string; value: string; active: boolean }> = ({ icon, label, value, active }) => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
    <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      {icon} {label}
    </span>
    <span style={{ color: active ? theme.color.ok : theme.color.textMuted, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
      {value}
    </span>
  </div>
);

/** Download mode: one tap drops the device to low power (TDP min, boost off, screen
 *  off while idle) while a game downloads unattended. Lists the effects it applies. */
export const EcoCard: FC<Props> = ({ state, onToggle }) => {
  const { t } = useI18n();
  const on = state.enabled;
  const level = state.tdp_unit === "level";

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", boxShadow: on ? `inset 0 0 0 1px ${theme.color.ok}` : theme.card.boxShadow }}>
        <ToggleField
          label={
            <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
              <LuLeaf size={16} color={theme.color.ok} /> {t("system.eco.title")}
            </span>
          }
          description={t("system.eco.desc")}
          checked={on}
          onChange={onToggle}
          bottomSeparator="none"
        />
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, marginTop: theme.space.sm, paddingTop: theme.space.sm, borderTop: `1px solid ${theme.color.hairline}` }}>
          <Effect
            icon={<LuZap size={12} />}
            label={t(level ? "system.eco.row.level" : "system.eco.row.tdp")}
            value={level ? t("system.eco.value.level", { level: state.tdp_min_w }) : `${state.tdp_min_w} W`}
            active={on}
          />
          <Effect
            icon={<LuMonitorOff size={12} />}
            label={t("system.eco.row.screen")}
            value={t(state.screen_off ? "system.eco.value.screenOff" : "system.eco.value.screenBlack")}
            active={on}
          />
          {state.affects_boost && (
            <Effect icon={<LuRocket size={12} />} label={t("system.eco.row.turbo")} value={t("system.eco.value.turboOff")} active={on} />
          )}
        </div>
      </div>
    </PanelSectionRow>
  );
};
