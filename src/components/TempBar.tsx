import { FC, memo } from "react";
import { clamp } from "../system/logic";
import { theme } from "../theme";

// Temperatures are shown on a 0..MAX_C scale; handheld silicon lives well under
// 100 °C, so a full bar = hot.
const MAX_C = 100;

interface Props {
  label: string;
  celsius: number;
}

/**
 * Compact read-only temperature bar (orange): label + value on one line, a thin
 * filled bar below. Bars (not gauges) keep the temperature block small so the
 * monitor stays a quick-glance dashboard above the curve editor.
 */
const TempBarImpl: FC<Props> = ({ label, celsius }) => {
  const fraction = clamp(celsius / MAX_C, 0, 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption }}>
        <span style={{ color: theme.color.textMuted }}>{label}</span>
        <span style={{ color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
          {Math.round(celsius)}°C
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: theme.color.hairline, overflow: "hidden" }}>
        <div style={{ width: `${fraction * 100}%`, height: "100%", background: theme.color.warn, borderRadius: 3 }} />
      </div>
    </div>
  );
};

export const TempBar = memo(TempBarImpl);
