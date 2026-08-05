import { FC } from "react";
import { SliderField } from "@decky/ui";

import { HudValueUnit, formatHudValue } from "../mangohud/editorUi";
import { theme } from "../theme";

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit: HudValueUnit;
  onChange: (value: number) => void;
}

export const HudSliderRow: FC<Props> = ({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}) => (
  <div
    data-hud-slider-row
    style={{
      display: "flex",
      flexDirection: "column",
      gap: theme.space.xs,
      minWidth: 0,
    }}
  >
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: theme.space.sm,
      }}
    >
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {label}
      </span>
      <output
        style={{
          fontSize: theme.font.caption,
          color: theme.color.textPrimary,
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {formatHudValue(value, unit)}
      </output>
    </div>
    <div
      data-hud-slider-track
      style={{
        width: "100%",
        minWidth: 0,
        boxSizing: "border-box",
        overflow: "hidden",
      }}
    >
      <SliderField
        value={value}
        min={min}
        max={max}
        step={step}
        showValue={false}
        className="pdc-hud-slider"
        onChange={onChange}
      />
    </div>
  </div>
);
