import { FC, memo } from "react";
import { Sparkline } from "./Sparkline";
import { rpmFraction } from "../fans/logic";
import { theme } from "../theme";

const SIZE = 88;
const STROKE = 7;
// The handheld blowers top out around here; the ring self-calibrates above this
// if a fan is ever seen spinning faster (see rpmFraction).
const NOMINAL_MAX_RPM = 7000;

interface Props {
  label: string;
  rpm: number;
  values: number[];
  // When it's the only fan, lay the ring and sparkline side by side so they fill
  // the full-width card (e.g. Steam Deck has a single fan) instead of a centered
  // ring with empty space beside it.
  wide?: boolean;
}

/**
 * One fan: a ring filled by speed (RPM ÷ max) with the live RPM in the center,
 * a generic label (Ventilador 1/2…) and a blue history sparkline. Fan-only — the
 * machine's two blowers run as one lock-step cooling system, so we don't tie a
 * fan to a CPU/GPU it doesn't independently cool.
 */
const FanChipImpl: FC<Props> = ({ label, rpm, values, wide = false }) => {
  const r = (SIZE - STROKE) / 2;
  const circ = 2 * Math.PI * r;
  const observedMax = values.length ? Math.max(...values, rpm) : rpm;
  const fraction = rpmFraction(rpm, observedMax, NOMINAL_MAX_RPM);

  const ring = (
    <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ flexShrink: 0 }}>
      <circle cx={SIZE / 2} cy={SIZE / 2} r={r} fill="none" stroke={theme.color.hairline} strokeWidth={STROKE} />
      <circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={r}
        fill="none"
        stroke={theme.color.accent}
        strokeWidth={STROKE}
        strokeDasharray={`${circ * fraction} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
      />
      <text x="50%" y="46%" textAnchor="middle" fill={theme.color.textPrimary} fontSize={17} fontWeight={700} style={{ fontVariantNumeric: "tabular-nums" }}>
        {rpm}
      </text>
      <text x="50%" y="64%" textAnchor="middle" fill={theme.color.textMuted} fontSize={9}>
        RPM
      </text>
    </svg>
  );
  const labelEl = <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{label}</div>;

  if (wide) {
    // Ring on the left; label + a taller sparkline fill the rest of the row.
    return (
      <div style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: theme.space.md, width: "100%" }}>
        {ring}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          {labelEl}
          <Sparkline values={values} color={theme.color.accent} height={40} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.xs, width: "100%" }}>
      {ring}
      <div style={{ textAlign: "center" }}>{labelEl}</div>
      <div style={{ width: "100%" }}>
        <Sparkline values={values} color={theme.color.accent} height={18} />
      </div>
    </div>
  );
};

// Memoized: the 1.5 s poll replaces the history array each tick; skip re-render
// when this fan's rpm/values are unchanged.
export const FanChip = memo(FanChipImpl);
