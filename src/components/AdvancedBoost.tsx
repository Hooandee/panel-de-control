import { CSSProperties, FC, useState } from "react";
import { Focusable, SliderField } from "@decky/ui";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

import { Levels, LevelBound, BoostMode, SteamDeckPptState } from "../api";
import { useI18n } from "../i18n";
import { offsetOf } from "../tdp/logic";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { theme } from "../theme";

interface AdvancedBoostProps {
  levels: Levels;
  mode: BoostMode;
  bounds: { pl2?: LevelBound; pl3?: LevelBound };
  ppt?: SteamDeckPptState | null;
  onSetMode: (mode: BoostMode) => void;
  onSetLevels: (off2: number, off3: number) => void;
}

const MODES: BoostMode[] = ["estable", "auto", "custom"];

export const AdvancedBoost: FC<AdvancedBoostProps> = ({
  levels,
  mode,
  bounds,
  ppt = null,
  onSetMode,
  onSetLevels,
}) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  const off2 = offsetOf(levels.pl2, levels.pl1);
  const off3 = offsetOf(levels.pl3, levels.pl2);

  const modeColor =
    mode === "estable" ? theme.color.ok : mode === "auto" ? theme.color.accent : theme.color.warn;
  const badge: CSSProperties = {
    fontSize: theme.font.caption,
    padding: "1px 7px",
    borderRadius: 999,
    color: modeColor,
    boxShadow: `inset 0 0 0 1px ${modeColor}`,
  };
  const Chevron = open ? LuChevronDown : LuChevronRight;
  const isDeckPpt = Boolean(ppt?.supported);

  const railRow = (
    label: string,
    value: number,
    floor: number,
    bound: LevelBound | undefined,
    onChange: (v: number) => void,
  ) => {
    // Absolute rail watts. Guard a 0-width range (floor at the ceiling): a min==max
    // SliderField divides by zero and fires onChange(NaN), poisoning the levels.
    const max = Math.max(floor + 1, bound?.max ?? floor + 1);
    const val = Math.min(Math.max(floor, Number.isFinite(value) ? value : floor), max);
    return (
    <div style={{ marginTop: theme.space.sm }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption }}>
        <span>{label}</span>
        <span style={{ color: theme.color.textMuted }}>{val} W</span>
      </div>
      {/* Steam's SliderField has a fixed intrinsic width (~panel width) + a
          Field margin:-16px that bleeds. A uniform scale(0.86) toward the centre
          shrinks it so it sits inside the card with margin even at max, keeping
          the handle round (scaleX alone made it oval); overflow clips the bleed. */}
      <div style={{ overflow: "hidden" }}>
        <div style={{ transform: "scale(0.86)" }}>
          <SliderField
            value={val}
            min={floor}
            max={max}
            step={1}
            onChange={onChange}
          />
        </div>
      </div>
    </div>
    );
  };

  return (
    <div style={{ ...theme.card, padding: theme.space.md, marginTop: theme.space.sm, overflow: "hidden" }}>
      <Focusable
        style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer" }}
        onActivate={() => setOpen((o) => !o)}
        onClick={() => setOpen((o) => !o)}
      >
        <Chevron size={16} color={theme.color.textMuted} />
        <span style={{ flex: 1 }}>{t(isDeckPpt ? "tdp.deckPpt.title" : "tdp.boost.title")}</span>
        {isDeckPpt && <span style={{ ...badge, color: theme.color.warn, boxShadow: `inset 0 0 0 1px ${theme.color.warn}` }}>{t("tdp.deckPpt.experimental")}</span>}
        <span style={badge}>{t(`tdp.boost.mode.${mode}`)}</span>
      </Focusable>

      {open && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
            {isDeckPpt ? t("tdp.deckPpt.hint") : t(`tdp.boost.hint.${mode}`)}
          </div>

          <div style={{ ...segmentGroupStyle, marginTop: theme.space.sm }}>
            {MODES.map((m) => (
              <Focusable
                key={m}
                style={{ ...segmentItemStyle(m === mode), flex: 1, padding: "4px 6px" }}
                onActivate={() => onSetMode(m)}
                onClick={() => onSetMode(m)}
              >
                {t(isDeckPpt && m === "estable" ? "tdp.deckPpt.off" : `tdp.boost.mode.${m}`)}
              </Focusable>
            ))}
          </div>

          {/* Resulting rails: the watts the firmware actually holds, for any mode. */}
          <div style={{
            display: "flex", justifyContent: "space-between",
            fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.sm,
          }}>
            <span>{isDeckPpt ? "SlowPPT" : "SPPT"} {levels.pl2} W</span>
            <span>{isDeckPpt ? "FastPPT" : "FPPT"} {levels.pl3} W</span>
          </div>

          {isDeckPpt && mode !== "estable" && ppt && (
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
              {t("tdp.deckPpt.applied", {
                slow: ppt.applied.slow ?? "—",
                fast: ppt.applied.fast ?? "—",
              })}
            </div>
          )}

          {mode === "custom" && (
            <>
              {bounds.pl2 && railRow(isDeckPpt ? "SlowPPT" : t("tdp.level.slow"), levels.pl2, levels.pl1, bounds.pl2, (v) => onSetLevels(Math.max(0, v - levels.pl1), off3))}
              {bounds.pl3 && railRow(isDeckPpt ? "FastPPT" : t("tdp.level.fast"), levels.pl3, levels.pl2, bounds.pl3, (v) => onSetLevels(off2, Math.max(0, v - levels.pl2)))}
            </>
          )}
        </>
      )}
    </div>
  );
};
