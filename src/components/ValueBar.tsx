import { FC, ReactNode } from "react";
import { SliderField } from "@decky/ui";
import { theme } from "../theme";

interface ValueBarProps {
  icon: ReactNode;
  label: string;
  /** 0..100 */
  percent: number;
  onChange: (percent: number) => void;
  /** When the underlying system control is unavailable on this device. */
  disabled?: boolean;
  unavailableLabel?: string;
}

/**
 * Labeled value control: icon + label, the exact numeric value shown large, and
 * a single gamepad/touch slider to set a precise value — the PdC answer to
 * Steam's native sliders that hide the number. The slider IS the bar (no second
 * decorative bar). Shows a degraded state (no slider) when unavailable.
 */
export const ValueBar: FC<ValueBarProps> = ({
  icon,
  label,
  percent,
  onChange,
  disabled = false,
  unavailableLabel,
}) => {
  const clamped = Math.min(100, Math.max(0, Math.round(percent)));

  return (
    <div
      style={{
        padding: theme.space.md,
        borderRadius: theme.radius.md,
        background: theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
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
          {disabled ? "—" : `${clamped}%`}
        </span>
      </div>

      {disabled ? (
        unavailableLabel && (
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
      ) : (
        // The slider is the single bar. Rendered directly — NOT in a
        // PanelSectionRow, whose negative margins would push it outside the card.
        <div style={{ marginTop: theme.space.xs }}>
          <SliderField
            value={clamped}
            min={0}
            max={100}
            step={1}
            showValue={false}
            onChange={onChange}
          />
        </div>
      )}
    </div>
  );
};
