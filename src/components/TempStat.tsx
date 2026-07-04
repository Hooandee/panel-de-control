import { FC, memo } from "react";
import { LuThermometer } from "react-icons/lu";

import { thermalZone } from "../fans/suggestLogic";
import { ZONE_COLOR } from "./ThermalScale";
import { theme } from "../theme";

interface Props {
  label: string;
  celsius: number;
  // "tile" (default): a hairline-bordered stat, meant to sit side by side
  // (Procesador · Gráfica). "hero": borderless + larger + centered — for the
  // Steam Deck "solo" merged card, where the temp shares one card with the fan
  // ring and a nested bordered box would be a container-in-a-container.
  variant?: "tile" | "hero";
}

/**
 * Temperature stat: a zone-colored thermometer icon + the number, with a small
 * label beneath. Two looks: a bordered tile (default, for the side-by-side
 * multi-sensor block) or a borderless, larger, centered "hero" (merged solo card).
 */
const TempStatImpl: FC<Props> = ({ label, celsius, variant = "tile" }) => {
  const color = ZONE_COLOR[thermalZone(celsius)];
  const hero = variant === "hero";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: theme.space.sm,
        ...(hero ? { justifyContent: "center" } : theme.tile),
      }}
    >
      <LuThermometer size={hero ? 30 : 22} color={color} style={{ flexShrink: 0 }} />
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontSize: hero ? 34 : 22, fontWeight: 700, lineHeight: 1.1, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
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
