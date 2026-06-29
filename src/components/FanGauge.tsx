import { FC, memo } from "react";
import { theme } from "../theme";

interface FanGaugeProps {
  label: string;
  rpm: number;
  /** 0..100 fan duty; null when the device exposes no PWM. */
  percent: number | null;
}

/**
 * Compact radial gauge: a ring filled to the fan's duty (when available) with
 * the live RPM in the center. Lightweight SVG (handheld perf).
 */
const FanGaugeImpl: FC<FanGaugeProps> = ({ label, rpm, percent }) => {
  const size = 96;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = c * (Math.min(100, Math.max(0, percent ?? 0)) / 100);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.xs }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={theme.color.hairline} strokeWidth={stroke} />
        {percent !== null && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={theme.color.accent}
            strokeWidth={stroke}
            strokeDasharray={`${dash} ${c}`}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
        <text
          x="50%"
          y="47%"
          textAnchor="middle"
          fill={theme.color.textPrimary}
          fontSize={20}
          fontWeight={700}
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {rpm}
        </text>
        <text x="50%" y="64%" textAnchor="middle" fill={theme.color.textMuted} fontSize={10}>
          RPM
        </text>
      </svg>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textAlign: "center" }}>
        {label}
        {percent !== null ? ` · ${percent}%` : ""}
      </div>
    </div>
  );
};

// Memoized: re-renders only when this fan's rpm/percent/label actually change.
export const FanGauge = memo(FanGaugeImpl);
