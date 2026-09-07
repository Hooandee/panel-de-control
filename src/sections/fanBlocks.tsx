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
import { DesktopFanCurves } from "../components/DesktopFanCurves";
import { FanInfo } from "../api";
import { desktopFanVisible } from "../fans/presentation";

const card = { ...theme.card, padding: theme.space.md } as const;

const tempLabel = (t: (k: string) => string, sensor: string) =>
  sensor === "CPU" ? t("fans.temp.cpu")
  : sensor === "GPU" ? t("fans.temp.gpu")
  : sensor === "GPU junction" ? t("fans.temp.gpuJunction")
  : sensor === "VRAM" ? t("fans.temp.vram") : sensor;

const DesktopFanTile: FC<{
  fan: FanInfo;
  values: number[];
  layout: "stack" | "wide";
  t: (key: string, vars?: Record<string, string | number>) => string;
}> = ({ fan, values, layout, t }) => {
  const channel = fan.channel!;
  const label = t(`desktop.fan.channel.${channel}`);
  return (
    <div style={{ ...theme.tile, display: "flex", minWidth: 0, flexDirection: "column", alignItems: "center", gap: theme.space.xs }}>
      <FanChip label={label} rpm={fan.rpm} values={values} maxRpm={fan.max_rpm} layout={layout} />
    </div>
  );
};

const FanRpmBlock: FC = () => {
  const { t } = useI18n();
  const { state, fanHistory } = useFanState();
  if (!state) return null;
  const visibleFans = state.fans.filter((fan) => desktopFanVisible(state.device_key, fan.channel));
  const solo = !state.desktop && isSolo(state);
  const soloFan = solo ? visibleFans[0] : null;
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
  if (visibleFans.length > 0) {
    return (
      <PanelSectionRow>
        <div style={{
          ...card,
          display: state.desktop ? "grid" : "flex",
          gridTemplateColumns: state.desktop
            ? (visibleFans.length === 1 ? "minmax(0, 1fr)" : "repeat(2, minmax(0, 1fr))")
            : undefined,
          gap: theme.space.sm,
        }}>
          {visibleFans.map((fan, i) => (
            state.desktop && fan.channel ? (
              <DesktopFanTile
                key={fan.channel}
                fan={fan}
                values={fanHistory[fan.label] ?? []}
                layout={visibleFans.length === 1 ? "wide" : "stack"}
                t={t}
              />
            ) : (
              <div key={fan.label} style={theme.tile}>
                <FanChip label={t("fans.fan", { n: i + 1 })} rpm={fan.rpm}
                         values={fanHistory[fan.label] ?? []}
                         layout={visibleFans.length === 1 ? "wide" : "stack"} />
              </div>
            )
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
      <div style={{ ...card, display: state.desktop ? "grid" : "flex", gridTemplateColumns: state.desktop ? "repeat(2, minmax(0, 1fr))" : undefined, flexWrap: state.desktop ? undefined : "wrap", gap: theme.space.sm }}>
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

  const firmwarePoints = useMemo<Point[] | null>(
    () => curve.state?.firmware_points?.map((p) => [p.temp, percentToPwm(p.pct)]) ?? null,
    [curve.state?.firmware_points],
  );

  const liveTemp = state && state.temps.length ? Math.max(...state.temps.map((x) => x.celsius)) : null;
  const curveState = curve.state;

  if (curveState?.independent) return <DesktopFanCurves initial={curveState} />;

  return (
    <>
      {curveState?.experimental_available && canControl && (
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
      {curveState && !curveState.supported
        && (curveState.firmware_mode || curveState.has_firmware_modes || curveState.kernel_pending
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

export function registerFanBlocks(): void {
  registerBlock("fanRpm", { sectionId: "fans", Component: FanRpmBlock });
  registerBlock("temps", {
    sectionId: "fans",
    Component: TempsBlock,
    useAvailable: () => tempsAvailable(useFanState().state),
  });
  registerBlock("curve", { sectionId: "fans", Component: CurveBlock });
}
