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
  ) => (
    <div style={{ marginTop: theme.space.sm }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption }}>
        <span>{label}</span>
        <span style={{ color: theme.color.textMuted }}>
          +{off} W → {totalFor(base, off, bound)} W
        </span>
      </div>
      <SliderField
        value={off}
        min={0}
        max={maxOffset(base, bound)}
        step={1}
        onChange={onChange}
      />
    </div>
  );

  return (
    <div style={{ ...theme.card, padding: theme.space.md, marginTop: theme.space.sm }}>
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
          {railRow(t("tdp.level.slow"), off2, levels.pl1, bounds.pl2, (o2) => onSetLevels(o2, off3))}
          {railRow(t("tdp.level.fast"), off3, levels.pl2, bounds.pl3, (o3) => onSetLevels(off2, o3))}
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
