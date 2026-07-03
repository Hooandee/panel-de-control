import { FC } from "react";
import { LuThermometer, LuContrast } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ContainedSlider } from "./ContainedSlider";
import { ColorState, ColorPreset } from "../api";

interface Props {
  state: ColorState;
  onChange: (patch: Partial<ColorPreset>) => void;
}

/** Global panel calibration: two intuitive, Apple-style knobs — Temperature
 *  (warm↔cool white balance) and Contrast (real, around mid-grey). Both bipolar
 *  (-100..100, 0 = neutral). Replaces the old raw R/G/B + gamma controls. */
export const ColorCalibration: FC<Props> = ({ state, onChange }) => {
  const { t } = useI18n();

  const row = (icon: React.ReactNode, label: string, ends: [string, string], value: number,
               key: "temperature" | "contrast") => (
    <div style={{ marginTop: theme.space.sm }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {icon}
        <span>{label}</span>
        <span style={{ marginLeft: "auto", color: theme.color.textPrimary, fontWeight: 700 }}>
          {value > 0 ? `+${value}` : value}
        </span>
      </div>
      <ContainedSlider value={value} min={-100} max={100} step={5} scale={0.75}
        onChange={(v) => onChange({ [key]: v })} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: theme.color.textMuted, marginTop: -2 }}>
        <span>{ends[0]}</span>
        <span>{ends[1]}</span>
      </div>
    </div>
  );

  return (
    <div>
      {row(<LuThermometer size={13} />, t("display.temperature"),
        [t("display.temp.cool"), t("display.temp.warm")], state.temperature, "temperature")}
      {row(<LuContrast size={13} />, t("display.contrast"),
        [t("display.contrast.low"), t("display.contrast.high")], state.contrast, "contrast")}
    </div>
  );
};
