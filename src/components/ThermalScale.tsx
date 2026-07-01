import { FC } from "react";
import { LuThermometer } from "react-icons/lu";

import { useI18n } from "../i18n";
import { thermalZone, ThermalZone, THERMAL_BOUNDS } from "../fans/suggestLogic";
import { clamp } from "../system/logic";
import { theme } from "../theme";

// A2 — make the temperature the game reaches CLEAR and give it meaning. The peak
// is the P98 of the observed histogram (band.peak) — a sustained max with real
// dwell, NOT an instantaneous spike (honest). The scale spans the handheld-APU
// range and colors each zone so a non-expert reads "how hot is this".
const SCALE_MIN = 40;
const SCALE_MAX = 95;

// Zone colors: green → amber → orange → red, matching thermalZone().
const ZONE_COLOR: Record<ThermalZone, string> = {
  cool: theme.color.ok,
  warm: theme.color.warn,
  hot: theme.color.boost,
  limit: theme.color.danger,
};

// Segment stops (°C) derived from THERMAL_BOUNDS (single source of truth) so the
// colored bar always matches thermalZone(): cool<60, warm 60–75, hot 75–88, limit ≥88.
const SEGMENTS: { zone: ThermalZone; from: number; to: number }[] = [
  { zone: "cool", from: SCALE_MIN, to: THERMAL_BOUNDS.warm },
  { zone: "warm", from: THERMAL_BOUNDS.warm, to: THERMAL_BOUNDS.hot },
  { zone: "hot", from: THERMAL_BOUNDS.hot, to: THERMAL_BOUNDS.limit },
  { zone: "limit", from: THERMAL_BOUNDS.limit, to: SCALE_MAX },
];

const pct = (t: number) => (clamp(t, SCALE_MIN, SCALE_MAX) - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100;

/** Peak-temperature readout + a colored zone scale with a marker at the peak. */
export const ThermalScale: FC<{ peak: number }> = ({ peak }) => {
  const { t } = useI18n();
  const zone = thermalZone(peak);
  const color = ZONE_COLOR[zone];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.sm }}>
        <LuThermometer size={16} color={color} style={{ alignSelf: "center" }} />
        <span style={{ flex: 1, fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("fans.suggest.peak.title")}
        </span>
        <span style={{ fontSize: theme.font.value, lineHeight: 1, color }}>
          {t("fans.suggest.peak.value", { peak: Math.round(peak) })}
        </span>
      </div>
      <div style={{ fontSize: theme.font.caption, color, textAlign: "right" }}>
        {t(`fans.suggest.zone.${zone}`)}
      </div>
      {/* colored zone bar + peak marker */}
      <div style={{ position: "relative", height: 8, borderRadius: 4, overflow: "hidden", display: "flex" }}>
        {SEGMENTS.map((s) => (
          <div key={s.zone} style={{ flex: s.to - s.from, background: ZONE_COLOR[s.zone], opacity: 0.85 }} />
        ))}
        <div
          style={{
            position: "absolute", top: -2, bottom: -2, left: `${pct(peak)}%`,
            width: 3, marginLeft: -1.5, borderRadius: 2,
            background: theme.color.textPrimary, boxShadow: "0 0 0 1px rgba(0,0,0,0.5)",
          }}
        />
      </div>
    </div>
  );
};
