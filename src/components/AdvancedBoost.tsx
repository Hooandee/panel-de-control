import { CSSProperties, FC, useState } from "react";
import { Focusable, SliderField } from "@decky/ui";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

import { Levels, LevelBound } from "../api";
import { useI18n } from "../i18n";
import { offsetOf, totalFor, maxOffset } from "../tdp/logic";
import { theme } from "../theme";

interface AdvancedBoostProps {
  levels: Levels;
  auto: boolean;
  bounds: { pl2?: LevelBound; pl3?: LevelBound };
  onSetLevels: (off2: number, off3: number) => void;
  onResetAuto: () => void;
}

export const AdvancedBoost: FC<AdvancedBoostProps> = ({
  levels,
  auto,
  bounds,
  onSetLevels,
  onResetAuto,
}) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  const off2 = offsetOf(levels.pl2, levels.pl1);
  const off3 = offsetOf(levels.pl3, levels.pl2);

  const badge: CSSProperties = {
    fontSize: theme.font.caption,
    padding: "1px 7px",
    borderRadius: 999,
    color: auto ? theme.color.ok : theme.color.warn,
    boxShadow: `inset 0 0 0 1px ${auto ? theme.color.ok : theme.color.warn}`,
  };
  const Chevron = open ? LuChevronDown : LuChevronRight;

  const railRow = (
    label: string,
    off: number,
    base: number,
    bound: LevelBound | undefined,
    onChange: (o: number) => void,
  ) => {
    // Guard against a 0-width range (rail already at the active ceiling): a
    // min==max SliderField divides by zero and fires onChange(NaN), which then
    // poisons the levels. Keep max >= 1 and the value finite + in range.
    const max = Math.max(1, maxOffset(base, bound));
    const val = Math.min(Math.max(0, Number.isFinite(off) ? off : 0), max);
    return (
    <div style={{ marginTop: theme.space.sm }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption }}>
        <span>{label}</span>
        <span style={{ color: theme.color.textMuted }}>
          +{val} W → {totalFor(base, val, bound)} W
        </span>
      </div>
      {/* Steam's SliderField has a fixed intrinsic width (~panel width) + a
          Field margin:-16px that bleeds. A uniform scale(0.86) toward the centre
          shrinks it so it sits inside the card with margin even at max, keeping
          the handle round (scaleX alone made it oval); overflow clips the bleed. */}
      <div style={{ overflow: "hidden" }}>
        <div style={{ transform: "scale(0.86)" }}>
          <SliderField
            value={val}
            min={0}
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
        <Chevron size={16} />
        <span style={{ flex: 1 }}>{t("tdp.advanced.title")}</span>
        <span style={badge}>{auto ? t("tdp.advanced.auto") : t("tdp.advanced.manual")}</span>
      </Focusable>

      {open && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
            {t("tdp.advanced.hint")}
          </div>
          {bounds.pl2 && railRow(t("tdp.level.slow"), off2, levels.pl1, bounds.pl2, (o2) => onSetLevels(o2, off3))}
          {bounds.pl3 && railRow(t("tdp.level.fast"), off3, levels.pl2, bounds.pl3, (o3) => onSetLevels(off2, o3))}
          {!auto && (
            <Focusable
              style={{
                marginTop: theme.space.md,
                padding: "6px 10px",
                borderRadius: theme.radius.sm,
                background: theme.color.surfaceRaised,
                boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
                textAlign: "center",
                cursor: "pointer",
                fontSize: theme.font.caption,
              }}
              onActivate={onResetAuto}
              onClick={onResetAuto}
            >
              {t("tdp.advanced.reset")}
            </Focusable>
          )}
        </>
      )}
    </div>
  );
};
