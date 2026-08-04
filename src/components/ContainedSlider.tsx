import { FC, ReactNode } from "react";
import { SliderField } from "@decky/ui";

import { theme } from "../theme";

interface Props {
  value: number;
  min: number;
  max: number;
  step?: number;
  showValue?: boolean;
  valueSuffix?: string;
  /** Optional compact label rendered beside the value, above the slider. */
  label?: ReactNode;
  /** Uniform shrink factor. Default 0.80; use a smaller value in tighter cards
   *  (e.g. the Pantalla cards) where 0.80 still bleeds past the right edge. */
  scale?: number;
  onChange: (value: number) => void;
}

/**
 * Steam's SliderField has a fixed intrinsic width (~the panel width) and a Field
 * with negative margins, so it bleeds outside custom cards. The fix is a
 * uniform scale (keeps the knob round) inside an overflow:hidden box. This wraps
 * that containment so call sites don't re-hand-roll it.
 */
export const ContainedSlider: FC<Props> = ({
  value, min, max, step, showValue, valueSuffix = "", label, scale = 0.8, onChange,
}) => (
  <div style={{ width: "100%", minWidth: 0 }}>
    {(label != null || showValue) && (
      <div style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: theme.space.sm,
        minWidth: 0,
        marginBottom: 2,
        padding: `0 ${theme.space.xs}px`,
      }}>
        {label != null && (
          <span style={{
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: theme.color.textMuted,
            fontSize: theme.font.caption,
          }}>
            {label}
          </span>
        )}
        {showValue && (
          <span
            data-testid="contained-slider-value"
            style={{
              flexShrink: 0,
              whiteSpace: "nowrap",
              color: theme.color.textPrimary,
              fontSize: theme.font.caption,
              fontWeight: 700,
            }}
          >
            {value}{valueSuffix}
          </span>
        )}
      </div>
    )}
    <div style={{ overflow: "hidden", width: "100%" }}>
      <div style={{ transform: `scale(${scale})`, transformOrigin: "center" }}>
        <SliderField
          value={value}
          min={min}
          max={max}
          step={step}
          showValue={false}
          label={label == null ? undefined : (
            <span style={{
              position: "absolute",
              width: 1,
              height: 1,
              padding: 0,
              margin: -1,
              overflow: "hidden",
              clip: "rect(0, 0, 0, 0)",
              whiteSpace: "nowrap",
              border: 0,
            }}>
              {label}
            </span>
          )}
          onChange={onChange}
        />
      </div>
    </div>
  </div>
);
