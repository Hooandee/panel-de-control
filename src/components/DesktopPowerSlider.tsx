import { FC } from "react";
import { SliderField } from "@decky/ui";

import { theme } from "../theme";

const SLIDER_SCALE = 0.85;

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}

export const DesktopPowerSlider: FC<Props> = ({ label, value, min, max, step = 1, onChange }) => (
  <div
    data-testid="desktop-slider-group"
    role="group"
    aria-label={label}
    style={{ width: "100%", minWidth: 0, boxSizing: "border-box", paddingInline: theme.space.sm, display: "flex", flexDirection: "column", gap: 3 }}
  >
    <div style={{ minWidth: 0, display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: theme.space.sm }}>
      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: theme.color.textMuted, fontSize: 10, fontWeight: 600 }}>
        {label}
      </span>
      <span style={{ flexShrink: 0, color: theme.color.textPrimary, fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
        {Math.round(value)} W
      </span>
    </div>
    <div
      data-testid="desktop-slider-viewport"
      style={{ width: "100%", minWidth: 0, overflow: "hidden", contain: "layout paint" }}
    >
      <div
        data-testid="desktop-slider-layout"
        style={{ width: `${100 / SLIDER_SCALE}%`, transform: `scale(${SLIDER_SCALE})`, transformOrigin: "left top" }}
      >
        <SliderField
          value={value}
          min={min}
          max={max}
          step={step}
          showValue={false}
          tooltip={label}
          onChange={onChange}
        />
      </div>
    </div>
    <div style={{ minWidth: 0, display: "flex", justifyContent: "space-between", color: theme.color.textMuted, fontSize: 9, fontVariantNumeric: "tabular-nums" }}>
      <span>{min} W</span>
      <span>{max} W</span>
    </div>
  </div>
);
