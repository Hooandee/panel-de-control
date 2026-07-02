import { FC, ReactNode } from "react";
import { PanelSectionRow, Spinner, Focusable } from "@decky/ui";
import { LuMaximize2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useFanState } from "../fans/useFanState";
import { useFanCurve } from "../fans/useFanCurve";
import { useFanSuggestion } from "../fans/useFanSuggestion";
import { FanChip } from "../components/FanChip";
import { TempStat } from "../components/TempStat";
import { FanCurveEditor } from "../components/FanCurveEditor";
import { openFanCurveModal } from "../components/FanCurveModal";
import { SectionBlocks } from "../customize/SectionBlocks";
import { theme } from "../theme";

const card = { ...theme.card, padding: theme.space.md } as const;

// Map a curated temp sensor token (CPU/GPU) to its localized display name
// ("Procesador" / "Gráfica"); unknown sensors show their raw label.
const tempLabel = (t: (k: string) => string, sensor: string) =>
  sensor === "CPU" ? t("fans.temp.cpu") : sensor === "GPU" ? t("fans.temp.gpu") : sensor;

/** Monitor (live RPM/temps) + fan-curve control (presets + draggable graph). */
export const VentiladoresSection: FC = () => {
  const { t } = useI18n();
  const { state, fanHistory } = useFanState();
  const curve = useFanCurve();
  const { suggestion } = useFanSuggestion(curve.game?.appid ?? null);

  if (!state) return <Spinner />;

  // NOTE: do NOT gate the whole section on the hwmon monitor's `supported`. Some
  // devices (Legion Go 2) expose NO hwmon fan but DO support a write backend (EC)
  // and report temps — gating here hid the curve editor + temps entirely. Render
  // whatever is available; show an honest note only when there is truly nothing.

  // Live max temp drives the "you are here" marker on the curve. Plain const (not
  // a hook) — it sits after the early returns above, and React.memo on
  // FanCurveGraph already skips re-renders when this primitive is unchanged.
  const liveTemp = state.temps.length ? Math.max(...state.temps.map((x) => x.celsius)) : null;
  const curveState = curve.state;

  // Three independent, reorderable/hideable blocks. Each renders nothing when its
  // data is absent (hwmon sees no fans, device has no temps, no write backend);
  // order + visibility layer on top via the customization store.
  const blocks: Record<string, ReactNode> = {
    // fans — one chip per physical fan (Ventilador 1/2…), side by side. When the
    // device exposes no readable fan (Legion Go original: no hwmon fan, no EC RPM),
    // say so honestly here rather than leaving the block silently empty.
    fanRpm: state.fans.length > 0 ? (
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", gap: theme.space.sm }}>
          {state.fans.map((fan, i) => (
            <div key={fan.label} style={theme.tile}>
              <FanChip label={t("fans.fan", { n: i + 1 })} rpm={fan.rpm}
                       values={fanHistory[fan.label] ?? []} layout={state.fans.length === 1 ? "wide" : "stack"} />
            </div>
          ))}
        </div>
      </PanelSectionRow>
    ) : (
      <PanelSectionRow>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("fans.unavailable")}
        </div>
      </PanelSectionRow>
    ),

    // temperatures — compact thermometer tiles side by side (Procesador · Gráfica);
    // extra sensors wrap to a second row.
    temps: state.temps.length > 0 && (
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
          {state.temps.map((tmp) => (
            <TempStat key={tmp.label} label={tempLabel(t, tmp.label)} celsius={tmp.celsius} />
          ))}
        </div>
      </PanelSectionRow>
    ),

    // fan-curve control (editor when the device supports writes; an honest note
    // otherwise — "unavailable" when we at least monitor fans, "no fans" when not).
    curve: (
      <>
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

              <FanCurveEditor control={curve} liveTemp={liveTemp} suggestion={suggestion} />
            </div>
          </PanelSectionRow>
        )}
        {/* Only when we CAN monitor fans but not control them (e.g. MSI Claw). The
            no-fans-at-all case is already stated honestly by the fanRpm block. */}
        {curveState && !curveState.supported && state.fans.length > 0 && (
          <PanelSectionRow>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("fans.curve.unsupported")}
            </div>
          </PanelSectionRow>
        )}
      </>
    ),
  };

  return <SectionBlocks sectionId="fans" blocks={blocks} />;
};
