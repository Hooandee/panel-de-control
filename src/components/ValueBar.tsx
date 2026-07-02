import { FC, ReactNode } from "react";
import { SliderField } from "@decky/ui";
import { theme } from "../theme";
import { clamp } from "../system/logic";

interface ValueBarProps {
  icon: ReactNode;
  label: string;
  /** 0..100 */
  percent: number;
  onChange: (percent: number) => void;
  /** The underlying system control is unavailable on this device. */
  disabled?: boolean;
  /** Supported but no real reading yet — show a placeholder, not a fake slider. */
  loading?: boolean;
  unavailableLabel?: string;
}

/**
 * Labeled value control: icon + label, the exact numeric value shown large, and
 * a single gamepad/touch slider to set a precise value — the PdC answer to
 * Steam's native sliders that hide the number. Honest about state: shows "—"
 * when unavailable and "…" while loading (never a fake 0% slider).
 */
export const ValueBar: FC<ValueBarProps> = ({
  icon,
  label,
  percent,
  onChange,
  disabled = false,
  loading = false,
  unavailableLabel,
}) => {
  const clamped = clamp(Math.round(percent), 0, 100);
  const value = disabled ? "—" : loading ? "…" : `${clamped}%`;

  return (
    <div
      style={{
        ...theme.card,
        padding: theme.space.md,
        opacity: disabled ? 0.5 : 1,
        overflow: "hidden", // contain the slider's focus highlight within the card
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: theme.space.sm,
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: theme.space.xs,
            fontSize: theme.font.body,
            color: theme.color.textPrimary,
          }}
        >
          {icon} {label}
        </span>
        <span
          style={{
            fontSize: theme.font.value,
            fontWeight: 700,
            lineHeight: 1,
            color: theme.color.textPrimary,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value}
        </span>
      </div>

      {disabled
        ? unavailableLabel && (
            <div
              style={{
                marginTop: theme.space.sm,
                fontSize: theme.font.caption,
                color: theme.color.textMuted,
              }}
            >
              {unavailableLabel}
            </div>
          )
        : !loading && (
            // The slider is the single bar. Rendered directly — NOT in a
            // PanelSectionRow, whose negative margins would push it outside the card.
            // Steam's SliderField has a fixed intrinsic width + a margin:-16px
            // bleed; a uniform scale(0.86) toward centre shrinks it so it sits
            // inside with margin even at max (round handle, unlike scaleX).
            <div style={{ marginTop: theme.space.xs, overflow: "hidden" }}>
              <div style={{ transform: "scale(0.80)", transformOrigin: "center" }}>
                <SliderField
                  value={clamped}
                  min={0}
                  max={100}
                  step={1}
                  showValue={false}
                  onChange={onChange}
                />
              </div>
            </div>
          )}
    </div>
  );
};
