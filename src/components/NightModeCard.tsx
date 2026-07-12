import { FC, ReactNode } from "react";
import { Focusable, ToggleField } from "@decky/ui";
import { LuMoon } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ContainedSlider } from "./ContainedSlider";
import { NightState, NightPatch } from "../api";
import { toHHMM, stepMinutes } from "../display/night";

interface Props {
  state: NightState;
  onChange: (patch: NightPatch) => void;
}

/** Night mode: an evening warm shift, always-on or scheduled, on top of the color. */
export const NightModeCard: FC<Props> = ({ state, onChange }) => {
  const { t } = useI18n();

  const btn = (label: string, onClick: () => void): ReactNode => (
    <Focusable
      style={{
        minWidth: 22, padding: "2px 6px", textAlign: "center",
        borderRadius: theme.radius.sm, background: theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        color: theme.color.textPrimary, fontSize: theme.font.body, cursor: "pointer",
      }}
      onActivate={onClick} onClick={onClick}
    >
      {label}
    </Focusable>
  );

  // A HH : MM stepper — hour steps by 60, minute by 15, both wrapping the day.
  const timeField = (label: string, value: number, key: "start" | "end"): ReactNode => {
    const [hh, mm] = toHHMM(value).split(":");
    const num = (v: string) => (
      <span style={{ minWidth: 20, textAlign: "center", fontWeight: 700, color: theme.color.textPrimary }}>{v}</span>
    );
    const step = (sign: number, size: number) =>
      btn(sign < 0 ? "−" : "+", () => onChange({ [key]: stepMinutes(value, sign, size) }));
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: theme.space.sm }}>
        <span style={{ flex: 1, fontSize: theme.font.caption, color: theme.color.textMuted }}>{label}</span>
        {step(-1, 60)}{num(hh)}{step(1, 60)}
        <span style={{ color: theme.color.textMuted }}>:</span>
        {step(-1, 15)}{num(mm)}{step(1, 15)}
      </div>
    );
  };

  return (
    <div style={{ ...theme.card, padding: theme.space.md, margin: `${theme.space.sm}px 0`, overflow: "hidden" }}>
      <ToggleField
        label={t("display.night")}
        description={t("display.night.desc")}
        checked={state.enabled}
        onChange={(v) => onChange({ enabled: v })}
        bottomSeparator="none"
      />

      {state.enabled && (
        <>
          <div style={{ marginTop: theme.space.sm }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <LuMoon size={13} />
              <span>{t("display.night.warmth")}</span>
              <span style={{ marginLeft: "auto", color: theme.color.textPrimary, fontWeight: 700 }}>{state.warmth}</span>
            </div>
            <ContainedSlider value={state.warmth} min={0} max={100} step={5} scale={0.75}
              onChange={(v) => onChange({ warmth: v })} />
          </div>

          <ToggleField
            label={t("display.night.schedule")}
            checked={state.schedule_enabled}
            onChange={(v) => onChange({ schedule_enabled: v })}
            bottomSeparator="none"
          />
          {state.schedule_enabled && (
            <>
              {timeField(t("display.night.start"), state.start, "start")}
              {timeField(t("display.night.end"), state.end, "end")}
            </>
          )}

          <div style={{
            marginTop: theme.space.sm, fontSize: theme.font.caption,
            color: state.active ? theme.color.accent : theme.color.textMuted,
          }}>
            {state.active ? t("display.night.on_now") : t("display.night.off_now")}
          </div>
        </>
      )}
    </div>
  );
};
