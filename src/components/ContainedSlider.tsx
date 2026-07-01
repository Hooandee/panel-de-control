import { FC } from "react";
import { SliderField } from "@decky/ui";

interface Props {
  value: number;
  min: number;
  max: number;
  step?: number;
  showValue?: boolean;
  onChange: (value: number) => void;
}

/**
 * Steam's SliderField has a fixed intrinsic width (~the panel width) and a Field
 * with negative margins, so it bleeds outside custom cards. The validated fix is a
 * uniform scale(0.86) (keeps the knob round) inside an overflow:hidden box. This
 * wraps that documented containment so call sites don't re-hand-roll it.
 */
export const ContainedSlider: FC<Props> = ({ value, min, max, step, showValue, onChange }) => (
  <div style={{ overflow: "hidden", width: "100%" }}>
    <div style={{ transform: "scale(0.86)" }}>
      <SliderField value={value} min={min} max={max} step={step} showValue={showValue} onChange={onChange} />
    </div>
  </div>
);
