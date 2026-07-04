import { FC, ReactNode } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { LuLeaf, LuRocket, LuSun, LuZap } from "react-icons/lu";

import { EcoState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  state: EcoState;
  /** Whether this device exposes a brightness API — gates the brightness effect
   *  so the card never claims a dim it can't perform (never-fake). */
  brightnessSupported: boolean;
  onToggle: (enabled: boolean) => void;
}

const Effect: FC<{ icon: ReactNode; label: string; active: boolean }> = ({ icon, label, active }) => (
  <div style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: active ? theme.color.ok : theme.color.textMuted }}>
    {icon} {label}
  </div>
);

/** Download mode: one tap drops the device to low power (TDP min, boost off, ambient
 *  screen dim) while a game downloads unattended. Shows the effects it will apply. */
export const EcoCard: FC<Props> = ({ state, brightnessSupported, onToggle }) => {
  const { t } = useI18n();
  const on = state.enabled;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: theme.space.card, boxShadow: on ? `inset 0 0 0 1px ${theme.color.ok}` : theme.card.boxShadow }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          <LuLeaf size={16} color={theme.color.ok} /> {t("system.eco.title")}
        </div>
        <ToggleField
          label={t("system.eco.desc")}
          checked={on}
          onChange={onToggle}
          bottomSeparator="none"
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.md, marginTop: theme.space.xs }}>
          <Effect icon={<LuZap size={12} />} label={t("system.eco.effect.tdp", { watts: state.tdp_min_w })} active={on} />
          {brightnessSupported && (
            <Effect icon={<LuSun size={12} />} label={t("system.eco.effect.brightness")} active={on} />
          )}
          {state.affects_boost && (
            <Effect icon={<LuRocket size={12} />} label={t("system.eco.effect.boost")} active={on} />
          )}
        </div>
      </div>
    </PanelSectionRow>
  );
};
