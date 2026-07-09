import { FC, ReactNode, useMemo } from "react";
import { PanelSectionRow, Focusable } from "@decky/ui";
import { LuMaximize2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useFanState } from "../fans/useFanState";
import { useFanCurve } from "../fans/useFanCurve";
import { useFanSuggestion } from "../fans/useFanSuggestion";
import { FanChip } from "../components/FanChip";
import { TempStat } from "../components/TempStat";
import { Sparkline } from "../components/Sparkline";
import { FanCurveEditor } from "../components/FanCurveEditor";
import { FanCurveGraph } from "../components/FanCurveGraph";
import { openFanCurveModal } from "../components/FanCurveModal";
import { Point, percentToPwm } from "../fans/curve";
import { Loading } from "../components/Loading";
import { SectionBlocks } from "../customize/SectionBlocks";
import { theme } from "../theme";

const card = { ...theme.card, padding: theme.space.md, marginBottom: theme.space.card } as const;

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

  // Read-only firmware curve (MSI Claw): map pct→pwm once per fetch so the memoized
  // FanCurveGraph isn't rebuilt on every 1.5 s monitor poll (points are static).
  // Hook stays BEFORE the early return (rules of hooks).
  const firmwarePoints = useMemo<Point[] | null>(
    () => curve.state?.firmware_points?.map((p) => [p.temp, percentToPwm(p.pct)]) ?? null,
    [curve.state?.firmware_points],
  );

  if (!state) return <Loading />;

  // NOTE: do NOT gate the whole section on the hwmon monitor's `supported`. Some
  // devices (Legion Go 2) expose NO hwmon fan but DO support a write backend (EC)
  // and report temps — gating here hid the curve editor + temps entirely. Render
  // whatever is available; show an honest note only when there is truly nothing.

  // Live max temp drives the "you are here" marker on the curve. Plain const (not
  // a hook) — it sits after the early returns above, and React.memo on
  // FanCurveGraph already skips re-renders when this primitive is unchanged.
  const liveTemp = state.temps.length ? Math.max(...state.temps.map((x) => x.celsius)) : null;
  const curveState = curve.state;

  // "Solo" layout (Steam Deck): EXACTLY one fan + one temp = a single cooling
  // system. Merge the two monitor cards into one — fan ring on the left, the
  // (APU) temperature beside it, and the fan's sparkline full-width below the
  // ring. Multi-fan/multi-temp machines keep the separate fanRpm + temps blocks.
  const solo = state.fans.length === 1 && state.temps.length === 1;
  const soloFan = solo ? state.fans[0] : null;
  const soloTemp = solo ? state.temps[0] : null;

  // Three independent, reorderable/hideable blocks. Each renders nothing when its
  // data is absent (hwmon sees no fans, device has no temps, no write backend);
  // order + visibility layer on top via the customization store.
  const blocks: Record<string, ReactNode> = {
    // fans — one chip per physical fan (Ventilador 1/2…), side by side. When the
    // device exposes no readable fan (Legion Go original: no hwmon fan, no EC RPM),
    // say so honestly here rather than leaving the block silently empty. In the
    // solo case this block hosts the MERGED fan+temp card (temp absorbed here; the
    // `temps` block renders nothing so the two aren't shown twice).
    fanRpm: solo && soloFan && soloTemp ? (
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
            <FanChip label={t("fans.fan", { n: 1 })} rpm={soloFan.rpm}
                     values={fanHistory[soloFan.label] ?? []} layout="ring" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <TempStat label={tempLabel(t, soloTemp.label)} celsius={soloTemp.celsius} variant="hero" />
            </div>
          </div>
          <Sparkline values={fanHistory[soloFan.label] ?? []} color={theme.color.accent} height={40} />
        </div>
      </PanelSectionRow>
    ) : state.fans.length > 0 ? (
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
    // extra sensors wrap to a second row. Empty in the solo case (the single temp
    // lives in the merged fanRpm card above — never render it twice).
    temps: !solo && state.temps.length > 0 && (
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
                <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>
                  {t("fans.curve.title")}
                </span>
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
        {/* Can't control, but the firmware curve is legible (MSI Claw EC): show it
            read-only with the live temperature marker on the curve. */}
        {curveState && !curveState.supported && firmwarePoints && (
          <PanelSectionRow>
            <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
              <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>
                {t("fans.firmware.title")}
              </span>
              <FanCurveGraph points={firmwarePoints} liveTemp={liveTemp} editable={false} onChange={() => {}} />
              <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {t("fans.firmware.note")}
              </span>
              <span style={{ fontSize: theme.font.caption, color: theme.color.accent }}>
                {t("fans.firmware.wip")}
              </span>
            </div>
          </PanelSectionRow>
        )}
        {/* Only when we CAN monitor fans but not control them AND can't read the
            firmware curve. The no-fans-at-all case is stated by the fanRpm block. */}
        {curveState && !curveState.supported && !firmwarePoints && state.fans.length > 0 && (
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
