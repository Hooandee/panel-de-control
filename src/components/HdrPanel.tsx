import { FC } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { LuPalette } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { HdrState, HdrPatch } from "../api";
import { shouldWarnHdrSaturation } from "../display/color";
import { ContainedSlider } from "./ContainedSlider";
import { InlineNotice } from "./CompactField";

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
  const hdrStatus = state.last_apply === false
    ? { key: "display.hdr.applyFailed", tone: "danger" as const }
    : state.confirmation === "accepted"
      ? { key: "display.hdr.accepted", tone: "warning" as const }
      : null;
  const saturationStatus = !state.enabled
    ? { key: "display.hdrSaturation.inactive", tone: "muted" as const }
    : warnSaturation
      ? { key: "display.hdrSaturation.warning", tone: "warning" as const }
      : null;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, width: "100%", boxSizing: "border-box", padding: theme.space.md, margin: `${theme.space.sm}px 0` }}>
        <ToggleField
          label={t("display.hdr")}
          description={t("display.hdr.desc")}
          checked={state.enabled}
          onChange={(v) => onChange({ enabled: v })}
          bottomSeparator="none"
        />
        {hdrStatus && (
          <InlineNotice tone={hdrStatus.tone}>
            {t(hdrStatus.key)}
          </InlineNotice>
        )}
        {saturation && (
          <div style={{ borderTop: `1px solid ${theme.color.hairline}`, marginTop: theme.space.sm, paddingTop: theme.space.md }}>
            <div
              data-testid="hdr-saturation-header"
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                alignItems: "start",
                gap: theme.space.sm,
              }}
            >
              <div data-testid="hdr-saturation-copy" style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <LuPalette size={16} color={theme.color.accent} style={{ flexShrink: 0 }} />
                  <span style={{ minWidth: 0, fontSize: theme.font.body, fontWeight: 600, lineHeight: 1.25, color: theme.color.textPrimary, overflowWrap: "anywhere" }}>
                    {t("display.hdrSaturation")}
                  </span>
                </div>
                {saturation.experimental && (
                  <span style={{
                    display: "inline-flex",
                    marginTop: theme.space.xs,
                    padding: "2px 6px",
                    borderRadius: 999,
                    background: "rgba(255,180,84,0.10)",
                    color: theme.color.warn,
                    fontSize: 10,
                    fontWeight: 700,
                    lineHeight: 1.2,
                  }}>
                    {t("device.experimental.badge")}
                  </span>
                )}
              </div>
              <span
                data-testid="hdr-saturation-value"
                style={{
                  whiteSpace: "nowrap",
                  fontSize: 21,
                  fontWeight: 700,
                  lineHeight: 1,
                  fontVariantNumeric: "tabular-nums",
                  color: theme.color.textPrimary,
                }}
              >
                {saturation.value}%
              </span>
            </div>
            <div style={{ marginTop: theme.space.xs, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.4, overflowWrap: "anywhere" }}>
              {t("display.hdrSaturation.desc")}
            </div>
            <ContainedSlider
              value={saturation.value}
              min={100}
              max={150}
              step={5}
              scale={0.75}
              onChange={saturation.onChange}
            />
            {saturationStatus && (
              <InlineNotice tone={saturationStatus.tone}>
                {t(saturationStatus.key)}
              </InlineNotice>
            )}
          </div>
        )}
      </div>
    </PanelSectionRow>
  );
};
