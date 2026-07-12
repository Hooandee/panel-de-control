import { FC, ReactNode, useState } from "react";
import { Focusable } from "@decky/ui";
import {
  LuThermometer, LuContrast, LuSun, LuDroplet, LuSparkles, LuBlend, LuMoon,
  LuChevronDown, LuChevronRight,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ContainedSlider } from "./ContainedSlider";
import { ColorState, ColorPreset, Calibration } from "../api";

interface Props {
  state: ColorState;
  onChange: (patch: Partial<ColorPreset>) => void;
}

type Key = keyof Calibration;

/** The "Avanzado" color lab: light/tone + colour balance (with a manual per-channel
 *  RGB sub-group). All global calibration; previewed live with the auto-revert. */
export const AdvancedColor: FC<Props> = ({ state, onChange }) => {
  const { t } = useI18n();
  const [rgbOpen, setRgbOpen] = useState(false);
  const toggleRgb = () => setRgbOpen((o) => !o);

  // A labelled slider; bipolar fields (min<0) show a signed value.
  const row = (
    icon: ReactNode, label: string, ends: [string, string],
    key: Key, min: number, max: number,
  ) => {
    const value = state[key];
    const shown = min < 0 && value > 0 ? `+${value}` : `${value}`;
    return (
      <div style={{ marginTop: theme.space.sm }} key={key}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {icon}
          <span>{label}</span>
          <span style={{ marginLeft: "auto", color: theme.color.textPrimary, fontWeight: 700 }}>{shown}</span>
        </div>
        <ContainedSlider value={value} min={min} max={max} step={min < 0 ? 5 : 1} scale={0.75}
          onChange={(v) => onChange({ [key]: v })} />
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: theme.color.textMuted, marginTop: -2 }}>
          <span>{ends[0]}</span>
          <span>{ends[1]}</span>
        </div>
      </div>
    );
  };

  const groupHeading = (label: string): ReactNode => (
    <div style={{ ...theme.sectionLabel, marginTop: theme.space.md, fontWeight: 700 }}>
      {label}
    </div>
  );

  return (
    <div>
      {groupHeading(t("display.group.tone"))}
      {row(<LuSun size={13} />, t("display.gamma"),
        [t("display.gamma.dark"), t("display.gamma.bright")], "gamma", -100, 100)}
      {/* Contrast is floored at -60 in the store so the panel can't go illegible; the
          slider matches that range so a drag never snaps back. */}
      {row(<LuContrast size={13} />, t("display.contrast"),
        [t("display.contrast.low"), t("display.contrast.high")], "contrast", -60, 60)}
      {row(<LuSparkles size={13} />, t("display.vibrance"),
        [t("display.vibrance.low"), t("display.vibrance.high")], "vibrance", -100, 100)}
      {row(<LuMoon size={13} />, t("display.black"),
        [t("display.black.deep"), t("display.black.lift")], "black", -100, 100)}

      {groupHeading(t("display.group.balance"))}
      {row(<LuThermometer size={13} />, t("display.temperature"),
        [t("display.temp.cool"), t("display.temp.warm")], "temperature", -100, 100)}
      {row(<LuDroplet size={13} />, t("display.hue"), ["−", "+"], "hue", -100, 100)}

      {/* Manual per-channel white balance — the nerdiest control, one level down. */}
      <Focusable
        style={{
          display: "flex", alignItems: "center", gap: 6, marginTop: theme.space.sm,
          padding: "6px 2px", cursor: "pointer",
          fontSize: theme.font.caption, color: theme.color.textPrimary,
        }}
        onActivate={toggleRgb} onClick={toggleRgb}
      >
        {rgbOpen ? <LuChevronDown size={13} /> : <LuChevronRight size={13} />}
        <LuBlend size={13} />
        <span>{t("display.rgb")}</span>
      </Focusable>
      {rgbOpen && (
        <div style={{ paddingLeft: 10 }}>
          {row(<span style={{ color: "#ff6b6b", fontWeight: 700 }}>R</span>, t("display.rgb.r"),
            ["50", "150"], "gain_r", 50, 150)}
          {row(<span style={{ color: "#5ad16a", fontWeight: 700 }}>G</span>, t("display.rgb.g"),
            ["50", "150"], "gain_g", 50, 150)}
          {row(<span style={{ color: "#5aa9ff", fontWeight: 700 }}>B</span>, t("display.rgb.b"),
            ["50", "150"], "gain_b", 50, 150)}
        </div>
      )}
    </div>
  );
};
