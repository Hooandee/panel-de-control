import { FC } from "react";
import { SliderField } from "@decky/ui";

interface Props {
  value: number;
  min: number;
  max: number;
  step?: number;
  showValue?: boolean;
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
export const ContainedSlider: FC<Props> = ({ value, min, max, step, showValue, scale = 0.8, onChange }) => (
  <div style={{ overflow: "hidden", width: "100%" }}>
    <div style={{ transform: `scale(${scale})`, transformOrigin: "center" }}>
      <SliderField value={value} min={min} max={max} step={step} showValue={showValue} onChange={onChange} />
    </div>
  </div>
);
