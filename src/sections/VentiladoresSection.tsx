import { FC } from "react";
import { PanelSectionRow, Spinner } from "@decky/ui";

import { useI18n } from "../i18n";
import { useFanState } from "../fans/useFanState";
import { FanGauge } from "../components/FanGauge";
import { Sparkline } from "../components/Sparkline";
import { theme } from "../theme";

// Cap temps shown so the panel stays clean; the device-aware layer will refine
// which sensors matter per device on-hardware.
const MAX_TEMPS = 6;

const card = { ...theme.card, padding: theme.space.md } as const;

/** Read-only live monitor: per-fan RPM gauge + sparkline, plus temperatures. */
export const VentiladoresSection: FC = () => {
  const { t } = useI18n();
  const { state, fanHistory, tempHistory } = useFanState();

  if (!state) return <Spinner />;

  if (!state.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("fans.unavailable")}
        </div>
      </PanelSectionRow>
    );
  }

  return (
    <>
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexWrap: "wrap", justifyContent: "space-around", gap: theme.space.md }}>
          {state.fans.map((f) => (
            <div key={f.label} style={{ flex: "1 1 120px", minWidth: 110 }}>
              <FanGauge label={f.label} rpm={f.rpm} percent={f.percent} />
              <div style={{ marginTop: theme.space.xs }}>
                <Sparkline values={fanHistory[f.label] ?? []} />
              </div>
            </div>
          ))}
        </div>
      </PanelSectionRow>

      {state.temps.length > 0 && (
        <PanelSectionRow>
          <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
            {state.temps.slice(0, MAX_TEMPS).map((tmp) => (
              <div key={tmp.label}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.body }}>
                  <span style={{ color: theme.color.textMuted }}>{tmp.label}</span>
                  <span style={{ color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
                    {tmp.celsius}°C
                  </span>
                </div>
                <Sparkline values={tempHistory[tmp.label] ?? []} height={22} color={theme.color.warn} />
              </div>
            ))}
          </div>
        </PanelSectionRow>
      )}
    </>
  );
};
