import { FC, memo } from "react";
import { LuThermometer } from "react-icons/lu";

import { thermalZone } from "../fans/suggestLogic";
import { ZONE_COLOR } from "./ThermalScale";
import { theme } from "../theme";

interface Props {
  label: string;
  celsius: number;
}

/**
 * Compact temperature tile: a zone-colored thermometer icon + the number, with a
 * small label beneath. Meant to sit side by side (Procesador · Gráfica) so the
 * temperature block reads as two clean stats, not a stack of bars.
 */
const TempStatImpl: FC<Props> = ({ label, celsius }) => {
  const color = ZONE_COLOR[thermalZone(celsius)];
  return (
    <div
      style={{
        ...theme.tile,
        display: "flex",
        alignItems: "center",
        gap: theme.space.sm,
      }}
    >
      <LuThermometer size={22} color={color} style={{ flexShrink: 0 }} />
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
          {Math.round(celsius)}°
        </span>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {label}
        </span>
      </div>
    </div>
  );
};

export const TempStat = memo(TempStatImpl);
