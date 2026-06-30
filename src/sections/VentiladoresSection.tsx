import { FC } from "react";
import { PanelSectionRow, Spinner, Focusable } from "@decky/ui";
import { LuMaximize2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useFanState } from "../fans/useFanState";
import { useFanCurve } from "../fans/useFanCurve";
import { FanChip } from "../components/FanChip";
import { TempBar } from "../components/TempBar";
import { FanCurveEditor } from "../components/FanCurveEditor";
import { openFanCurveModal } from "../components/FanCurveModal";
import { theme } from "../theme";

const card = { ...theme.card, padding: theme.space.md } as const;

const chipBox = {
  flex: "1 1 0",
  minWidth: 0,
  padding: theme.space.sm,
  borderRadius: theme.radius.sm,
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
} as const;

// Map a curated temp sensor token (CPU/GPU) to its localized display name
// ("Procesador" / "Gráfica"); unknown sensors show their raw label.
const tempLabel = (t: (k: string) => string, sensor: string) =>
  sensor === "CPU" ? t("fans.temp.cpu") : sensor === "GPU" ? t("fans.temp.gpu") : sensor;

/** Monitor (live RPM/temps) + fan-curve control (presets + draggable graph). */
export const VentiladoresSection: FC = () => {
  const { t } = useI18n();
  const { state, fanHistory } = useFanState();
  const curve = useFanCurve();

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

  // Live max temp drives the "you are here" marker on the curve. Plain const (not
  // a hook) — it sits after the early returns above, and React.memo on
  // FanCurveGraph already skips re-renders when this primitive is unchanged.
  const liveTemp = state.temps.length ? Math.max(...state.temps.map((x) => x.celsius)) : null;
  const curveState = curve.state;

  return (
    <>
      {/* fans — one chip per physical fan (Ventilador 1/2…), side by side */}
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", gap: theme.space.sm }}>
          {state.fans.map((fan, i) => (
            <div key={fan.label} style={chipBox}>
              <FanChip label={t("fans.fan", { n: i + 1 })} rpm={fan.rpm} values={fanHistory[fan.label] ?? []} />
            </div>
          ))}
        </div>
      </PanelSectionRow>

      {/* temperatures — compact orange bars (Procesador + Gráfica), not gauges */}
      {state.temps.length > 0 && (
        <PanelSectionRow>
          <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
            {state.temps.map((tmp) => (
              <TempBar key={tmp.label} label={tempLabel(t, tmp.label)} celsius={tmp.celsius} />
            ))}
          </div>
        </PanelSectionRow>
      )}

      {/* fan-curve control (only when the device supports writes) */}
      {curveState?.supported && (
        <PanelSectionRow>
          <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("fans.curve.title")}</span>
              <Focusable
                style={{ display: "flex", alignItems: "center", padding: 4, borderRadius: theme.radius.sm, color: theme.color.textMuted, cursor: "pointer" }}
                onActivate={() => openFanCurveModal(liveTemp, curve.refresh)}
                onClick={() => openFanCurveModal(liveTemp, curve.refresh)}
                title={t("fans.curve.expand")}
              >
                <LuMaximize2 size={16} />
              </Focusable>
            </div>

            <FanCurveEditor control={curve} liveTemp={liveTemp} />
          </div>
        </PanelSectionRow>
      )}

      {/* device monitors fans but has no supported write backend — say so honestly */}
      {curveState && !curveState.supported && (
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("fans.curve.unsupported")}
          </div>
        </PanelSectionRow>
      )}
    </>
  );
};
