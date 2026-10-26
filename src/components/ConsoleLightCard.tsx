import { FC } from "react";
import { Focusable } from "@decky/ui";
import { LuCheck, LuLamp } from "react-icons/lu";

import { ConsoleLightPreset, ConsoleState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { presetDetail, presetLabel, swatchBackground } from "../system/consoleLight";
import { Collapsible } from "./Collapsible";

const Tile: FC<{ preset: ConsoleLightPreset; active: boolean; onPick: () => void }> = ({ preset, active, onPick }) => {
  const { t } = useI18n();
  const detail = presetDetail(preset.id, t);
  return (
    <Focusable
      onActivate={onPick}
      onClick={onPick}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", gap: 6, minWidth: 0,
        padding: `${theme.space.sm}px ${theme.space.xs}px`, borderRadius: theme.radius.sm, cursor: "pointer",
        background: active ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.04)",
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
      }}
    >
      <span style={{
        position: "relative", width: 26, height: 26, borderRadius: "50%", background: swatchBackground(preset.id),
        boxShadow: preset.id === "off" ? `inset 0 0 0 2px ${theme.color.textMuted}` : "0 0 10px rgba(255,255,255,0.15)",
      }}>
        {active && (
          <span
            style={{
              position: "absolute", right: -5, bottom: -5, width: 15, height: 15, borderRadius: "50%",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: theme.color.ok, color: theme.color.onAccent,
            }}
          >
            <LuCheck size={11} strokeWidth={3} />
          </span>
        )}
      </span>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textPrimary, textAlign: "center", lineHeight: 1.2 }}>
        {presetLabel(preset.id, t)}
      </span>
      {detail && (
        <span style={{ fontSize: theme.font.caption - 1, color: theme.color.textMuted, textAlign: "center", lineHeight: 1.2 }}>{detail}</span>
      )}
    </Focusable>
  );
};

const Grid: FC<{ presets: ConsoleLightPreset[]; active: string | null; onPick: (id: string) => void }> = ({ presets, active, onPick }) => (
  <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 6 }}>
    {presets.map((preset) => (
      <Tile key={preset.id} preset={preset} active={preset.id === active} onPick={() => onPick(preset.id)} />
    ))}
  </Focusable>
);

export const ConsoleLightCard: FC<{ state: ConsoleState; onPick: (id: string) => void }> = ({ state, onPick }) => {
  const { t } = useI18n();
  const led = state.led!;
  const fixed = led.presets.filter((preset) => !preset.animated);
  const animated = led.presets.filter((preset) => preset.animated);
  const failed = led.last && !led.last.ok;
  const heading = (key: string) => (
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, letterSpacing: 0.2 }}>{t(key)}</span>
  );
  return (
    <Collapsible
      id="console-light"
      icon={<LuLamp size={16} />}
      title={t("console.light.title")}
      summary={led.active ? presetLabel(led.active, t) : t("console.light.untouched")}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {heading("console.light.fixed")}
        <Grid presets={fixed} active={led.active} onPick={onPick} />
        {animated.length > 0 && heading("console.light.animated")}
        {animated.length > 0 && <Grid presets={animated} active={led.active} onPick={onPick} />}
        <span style={{ fontSize: theme.font.caption, color: failed ? theme.color.warn : theme.color.textMuted, lineHeight: 1.4 }}>
          {t(failed ? "console.light.failed" : "console.light.note")}
        </span>
      </div>
    </Collapsible>
  );
};
