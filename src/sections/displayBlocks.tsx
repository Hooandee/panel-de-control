import { FC } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuGlobe, LuPalette, LuSlidersHorizontal, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { isNativeColor, isCalibrated } from "../display/color";
import { usePantalla } from "../display/pantallaContext";
import { ContainedSlider } from "../components/ContainedSlider";
import { Collapsible } from "../components/Collapsible";
import { OledLookCard } from "../components/OledLookCard";
import { AdvancedColor } from "../components/AdvancedColor";
import { NightModeCard } from "../components/NightModeCard";
import { HdrPanel } from "../components/HdrPanel";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
import { registerBlock } from "../customize/blocks";

const OledBlock: FC = () => {
  const { color } = usePantalla();
  if (!color.state?.oled_look) return null;
  const active = !isNativeColor(color.state);
  return (
    <div style={{ marginTop: theme.space.sm }}>
      <OledLookCard active={active} onApply={color.onOledLook} onReset={color.onReset} />
    </div>
  );
};

const ColorBlock: FC = () => {
  const { t } = useI18n();
  const { color } = usePantalla();
  const state = color.state;
  if (!state) return null;
  const active = !isNativeColor(state);
  const chip = (on: boolean) => ({ ...segmentItemStyle(on), flex: 1, padding: "6px 4px" });
  return (
    <>
      <PanelSectionRow>
        <div style={{ ...theme.card, padding: theme.space.md, marginTop: theme.space.sm, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <LuSparkles size={16} color={theme.color.accent} />
            <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
              {t("display.look")}
            </span>
          </div>
          <Focusable style={segmentGroupStyle}>
            {state.presets.map((key) => (
              <Focusable key={key} style={chip(state.active_preset === key)}
                onActivate={() => color.onPreset(key)} onClick={() => color.onPreset(key)}>
                {t(`display.look.${key}`)}
              </Focusable>
            ))}
          </Focusable>
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ ...theme.card, padding: theme.space.md, margin: `${theme.space.sm}px 0`, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}>
            <LuPalette size={16} color={theme.color.accent} />
            <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
              {t("display.saturation")}
            </span>
            <span style={{ marginLeft: "auto", fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
              {state.saturation}%
            </span>
          </div>
          <ContainedSlider value={state.saturation} min={0} max={200} step={5}
            scale={0.75} onChange={color.onSaturation} />
        </div>
      </PanelSectionRow>
      <Collapsible
        id="color-advanced"
        icon={<LuSlidersHorizontal size={16} />}
        title={t("display.advanced")}
        summary={isCalibrated(state) ? t("display.custom") : t("display.native")}
      >
        <AdvancedColor state={state} onChange={color.onCalibration} />
        {active && (
          <Focusable
            style={{
              display: "flex", justifyContent: "center", marginTop: 10, padding: "6px 12px",
              borderRadius: theme.radius.sm, background: theme.color.surfaceRaised,
              boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
              color: theme.color.textPrimary, fontSize: theme.font.body, cursor: "pointer",
            }}
            onActivate={color.onReset} onClick={color.onReset}
          >
            {t("display.reset")}
          </Focusable>
        )}
      </Collapsible>
    </>
  );
};

const HdrBlock: FC = () => {
  const { hdr } = usePantalla();
  if (!hdr.state?.supported) return null;
  return (
    <PanelSectionRow>
      <HdrPanel state={hdr.state} onChange={hdr.update} />
    </PanelSectionRow>
  );
};

const NightBlock: FC = () => {
  const { t } = useI18n();
  const { night } = usePantalla();
  if (!night.state?.supported) return null;
  return (
    <>
      <PanelSectionRow>
        <div style={{ display: "flex", alignItems: "center", gap: 8, margin: `${theme.space.md}px 0 ${theme.space.xs}px`, color: theme.color.textMuted }}>
          <LuGlobe size={13} />
          <span style={{ fontSize: theme.font.caption }}>{t("display.general")}</span>
          <div style={{ flex: 1, height: 1, background: theme.color.hairline }} />
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <NightModeCard state={night.state} onChange={night.update} />
      </PanelSectionRow>
    </>
  );
};

export function registerDisplayBlocks(): void {
  registerBlock("oled", {
    sectionId: "display",
    Component: OledBlock,
    useAvailable: () => !!usePantalla().color.state?.oled_look,
  });
  registerBlock("color", { sectionId: "display", Component: ColorBlock });
  registerBlock("hdr", {
    sectionId: "display",
    Component: HdrBlock,
    useAvailable: () => !!usePantalla().hdr.state?.supported,
  });
  registerBlock("night", {
    sectionId: "display",
    Component: NightBlock,
    useAvailable: () => !!usePantalla().night.state?.supported,
  });
}
