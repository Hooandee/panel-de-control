import { FC } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { LuPalette } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { HdrState, HdrPatch } from "../api";
import { shouldWarnHdrSaturation } from "../display/color";
import { ContainedSlider } from "./ContainedSlider";

interface SaturationControl {
  value: number;
  experimental: boolean;
  onChange: (value: number) => void;
}

interface Props {
  state: HdrState;
  onChange: (patch: HdrPatch) => void;
  saturation?: SaturationControl;
}

export const HdrPanel: FC<Props> = ({ state, onChange, saturation }) => {
  const { t } = useI18n();
  const warnSaturation = saturation
    ? shouldWarnHdrSaturation(saturation.value)
    : false;
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, margin: `${theme.space.sm}px 0`, overflow: "hidden" }}>
        <ToggleField
          label={t("display.hdr")}
          description={t("display.hdr.desc")}
          checked={state.enabled}
          onChange={(v) => onChange({ enabled: v })}
          bottomSeparator="none"
        />
        {state.last_apply === false && (
          <div style={{ color: theme.color.danger, fontSize: theme.font.caption, lineHeight: 1.35 }}>
            {t("display.hdr.applyFailed")}
          </div>
        )}
        {state.confirmation === "accepted" && (
          <div style={{ color: theme.color.warn, fontSize: theme.font.caption, lineHeight: 1.35 }}>
            {t("display.hdr.accepted")}
          </div>
        )}
        {saturation && (
          <div style={{ borderTop: `1px solid ${theme.color.hairline}`, marginTop: theme.space.sm, paddingTop: theme.space.md }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}>
              <LuPalette size={16} color={theme.color.accent} />
              <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
                {t("display.hdrSaturation")}
              </span>
              {saturation.experimental && (
                <span style={{ color: theme.color.warn, fontSize: theme.font.caption, fontWeight: 700 }}>
                  {t("device.experimental.badge")}
                </span>
              )}
              <span style={{ marginLeft: "auto", fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
                {saturation.value}%
              </span>
            </div>
            <ContainedSlider
              value={saturation.value}
              min={100}
              max={150}
              step={5}
              scale={0.75}
              onChange={saturation.onChange}
            />
            <div style={{
              marginTop: theme.space.xs,
              color: warnSaturation ? theme.color.warn : theme.color.textMuted,
              fontSize: theme.font.caption,
              lineHeight: 1.35,
            }}>
              {t(warnSaturation
                ? "display.hdrSaturation.warning"
                : saturation.experimental
                  ? "display.hdrSaturation.experimental"
                  : "display.hdrSaturation.desc")}
            </div>
          </div>
        )}
      </div>
    </PanelSectionRow>
  );
};
