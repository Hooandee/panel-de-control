import { FC, useMemo } from "react";
import { PanelSectionRow, Focusable } from "@decky/ui";
import { LuMaximize2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useFanState } from "../fans/useFanState";
import { useFanCurve } from "../fans/useFanCurve";
import { useFanSuggestion } from "../fans/useFanSuggestion";
import { fanCurveNotice } from "../fans/notice";
import { isSolo, tempsAvailable } from "../fans/logic";
import { FanChip } from "../components/FanChip";
import { TempStat } from "../components/TempStat";
import { Sparkline } from "../components/Sparkline";
import { FanCurveEditor } from "../components/FanCurveEditor";
import { FanCurveGraph } from "../components/FanCurveGraph";
import { ExperimentalFanCard } from "../components/ExperimentalFanCard";
import { FanResetButton } from "../components/FanResetButton";
import { openFanCurveModal } from "../components/FanCurveModal";
import { Point, percentToPwm } from "../fans/curve";
import { registerBlock } from "../customize/blocks";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { theme } from "../theme";

const card = { ...theme.card, padding: theme.space.md, marginBottom: theme.space.card } as const;

// Map a curated temp sensor token (CPU/GPU) to its localized display name
// ("Procesador" / "Gráfica"); unknown sensors show their raw label.
const tempLabel = (t: (k: string) => string, sensor: string) =>
  sensor === "CPU" ? t("fans.temp.cpu") : sensor === "GPU" ? t("fans.temp.gpu") : sensor;

// Ventiladores blocks: the live monitor (RPM/temps) + the fan-curve control. Each
// owns its data via the shared useFanState monitor (one poll, ref-counted). In the
// "solo" case (one fan + one temp) the temp is merged into the fan card, so the
// temps block reports itself unavailable and renders nothing.

const FanRpmBlock: FC = () => {
  const { t } = useI18n();
  const { state, fanHistory } = useFanState();
  if (!state) return null;
  const solo = isSolo(state);
  const soloFan = solo ? state.fans[0] : null;
  const soloTemp = solo ? state.temps[0] : null;
  if (solo && soloFan && soloTemp) {
    return (
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
    );
  }
  if (state.fans.length > 0) {
    return (
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
    );
  }
  return (
    <PanelSectionRow>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("fans.unavailable")}
      </div>
    </PanelSectionRow>
  );
};

const TempsBlock: FC = () => {
  const { t } = useI18n();
  const { state } = useFanState();
  if (!tempsAvailable(state) || !state) return null;
  return (
    <PanelSectionRow>
      <div style={{ ...card, display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
        {state.temps.map((tmp) => (
          <TempStat key={tmp.label} label={tempLabel(t, tmp.label)} celsius={tmp.celsius} />
        ))}
      </div>
    </PanelSectionRow>
  );
};

const CurveBlock: FC = () => {
  const { t } = useI18n();
  const { state } = useFanState();
  const curve = useFanCurve();
  const { suggestion } = useFanSuggestion(curve.game?.appid ?? null);
  const disabled = useModules();
  const canControl = effectiveEnabled("fanControl", disabled);
  const canLearn = effectiveEnabled("learning", disabled);

  // Read-only firmware curve (MSI Claw): map pct→pwm once per fetch so the memoized
  // FanCurveGraph isn't rebuilt on every 1.5 s monitor poll (points are static).
  const firmwarePoints = useMemo<Point[] | null>(
    () => curve.state?.firmware_points?.map((p) => [p.temp, percentToPwm(p.pct)]) ?? null,
    [curve.state?.firmware_points],
  );

  // Live max temp drives the "you are here" marker on the curve.
  const liveTemp = state && state.temps.length ? Math.max(...state.temps.map((x) => x.celsius)) : null;
  const curveState = curve.state;

  return (
    <>
      {/* Legion Go S: opt-in to the unofficial EC channel. Enabling flips
          `supported` on → the editor below renders. */}
      {curveState?.experimental_available && (
        <ExperimentalFanCard enabled={curveState.experimental_enabled} onToggle={curve.onExperimental} />
      )}
      {curveState?.supported && canControl && (
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

            <FanCurveEditor control={curve} liveTemp={liveTemp} suggestion={canLearn ? suggestion : null} />

            {curveState.resettable && <FanResetButton onReset={curve.onReset} />}
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
      {/* Uncontrollable fan: a firmware mode governs it (Legion Go original, shown
          even with no fan detected), or the honest OS note when we can monitor but
          not control and there's no firmware curve. */}
      {curveState && !curveState.supported
        && (curveState.firmware_mode || curveState.has_firmware_modes
            || (!firmwarePoints && !curveState.experimental_available && (state?.fans.length ?? 0) > 0)) && (
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {fanCurveNotice(curveState, t)}
          </div>
        </PanelSectionRow>
      )}
    </>
  );
};

registerBlock("fanRpm", { sectionId: "fans", Component: FanRpmBlock });
registerBlock("temps", {
  sectionId: "fans",
  Component: TempsBlock,
  useAvailable: () => tempsAvailable(useFanState().state),
});
registerBlock("curve", { sectionId: "fans", Component: CurveBlock });
