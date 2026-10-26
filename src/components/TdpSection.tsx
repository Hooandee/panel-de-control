import { PanelSectionRow, SliderField, Focusable, ToggleField } from "@decky/ui";
import { FC, useCallback, useEffect, useMemo, useState } from "react";

import { TdpState, TdpScope, PowerDraw, BoostMode, PowerPresetState } from "../api";
import { resetWatts } from "../tdp/logic";
import { extraZone, manualCeiling } from "../tdp/extraZone";
import { PresetItem } from "../tdp/powerPresets";
import { resolveLivePresets } from "../tdp/livePresets";
import { openPowerPresetsModal } from "./PowerPresetsModal";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { PowerArc } from "./PowerArc";
import { isLevelUnit, levelFrequencySummary } from "../tdp/unit";
import { PowerTarget, PowerTargetTabs } from "./PowerTargetTabs";
import { autoGpuLevel } from "../tdp/autoView";
import { Presets } from "./Presets";
import { FirmwareModes } from "./FirmwareModes";
import { AdvancedBoost } from "./AdvancedBoost";
import { TdpSuggestionCard } from "./TdpSuggestionCard";
import { TdpMonitorNotice } from "./TdpMonitorNotice";
import { TdpOwnershipStatus } from "./TdpOwnershipStatus";
import { ExperimentalLabel } from "./ExperimentalBadge";
import { ownershipMessage, ownershipView } from "../tdp/ownership";

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  power: PowerDraw | null;
  onWatts: (watts: number) => void;
  onGpuLevel?: (level: number | null) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onSetMode: (mode: BoostMode) => void;
  // Apply the learned-band suggestion as a FIXED PL1 (also turns auto-TDP off).
  onApplySuggestion: (watts: number) => void;
  // Select a firmware performance mode (Legion Go original); "custom" via the slider.
  onFirmwareMode: (mode: string) => void;
  onLowBatteryHold: (enabled: boolean) => void;
  // Master switch off: show only the live arc + a notice, hide write controls.
  monitorOnly?: boolean;
  // Flip the master switch back on from the monitor notice.
  onReactivate?: () => void;
  // Custom power-preset library (built-in watts resolved from `tdp.presets`).
  presets: PowerPresetState | null;
  refreshPresets: () => void;
  onApplyPreset: (item: PresetItem) => void;
  /** The console firmware owns the power budget (PS5): explain it instead of a bare notice. */
  consoleManaged?: boolean;
}

const STEAM_DECK_NOMINAL_MAX_W = 15;

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, power, onWatts, onGpuLevel, onSetLevels, onSetMode, onApplySuggestion, onFirmwareMode, onLowBatteryHold, monitorOnly, onReactivate, presets, refreshPresets, onApplyPreset, consoleManaged }) => {
  const { t } = useI18n();
  const [target, setTarget] = useState<PowerTarget>("cpu");
  const targetContext = `${scope}:${tdp?.appid ?? ""}`;
  useEffect(() => setTarget("cpu"), [targetContext]);

  // Memoized (and above the early returns) so re-renders don't rebuild the chip list.
  // Falls back to a builtins-only library if the custom library hasn't loaded.
  const resolved = useMemo(
    () => (tdp ? resolveLivePresets(tdp, presets, scope, t) : null),
    [tdp, presets, scope, t],
  );

  const storedGpu = tdp ? (scope === "global" ? tdp.global_gpu_level : tdp.gpu_level) ?? null : null;
  const gpuResolved = useMemo(() => {
    if (!tdp || storedGpu === null) return null;
    const asGpu = { ...tdp, watts: storedGpu, global_watts: storedGpu };
    return resolveLivePresets(asGpu, presets, scope, t);
  }, [tdp, storedGpu, presets, scope, t]);

  // Stable identity so the memoized chip row doesn't re-render on every tick. Edit range is
  // the charger ceiling so a charger-made preset isn't clipped when edited on battery.
  const onEditPresets = useCallback(() => {
    if (!tdp) return;
    openPowerPresetsModal({
      builtinWatts: tdp.presets,
      onAc: tdp.on_ac,
      currentWatts: target === "gpu" && storedGpu !== null
        ? storedGpu
        : (scope === "global" ? tdp.global_watts : tdp.watts),
      min: tdp.request_min ?? tdp.limits.min,
      max: tdp.limits.max_ac,
      supportsAdvanced: tdp.supports_advanced,
      // Absolute rail ceilings; the editor bounds each margin against the preset's own PL1
      // so a rail can never exceed its firmware max.
      pl2Max: tdp.level_limits.pl2?.max ?? tdp.limits.max_ac,
      pl3Max: tdp.level_limits.pl3?.max ?? tdp.limits.max_ac,
      onClose: refreshPresets,
      formatValue: isLevelUnit(tdp.unit) ? (level) => t("tdp.level.value", { level }) : undefined,
    });
  }, [tdp, scope, refreshPresets, t, target, storedGpu]);

  if (!tdp) return <Loading />;

  if (!tdp.supported && consoleManaged) {
    return (
      <PanelSectionRow>
        <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
            {t("tdp.console.title")}
          </span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
            {t("tdp.console.body")}
          </span>
        </div>
      </PanelSectionRow>
    );
  }

  if (!tdp.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  }

  const view =
    scope === "global"
      ? { watts: tdp.global_watts, levels: tdp.global_requested_levels ?? tdp.global_levels, mode: tdp.global_boost_mode }
      : { watts: tdp.watts, levels: tdp.requested_levels ?? tdp.levels, mode: tdp.boost_mode };
  const requestMin = tdp.request_min ?? tdp.limits.min;
  // Active ceiling: on battery the device-aware cap (max), on charger max_ac.
  // Never offer more than the current power source can deliver.
  const activeMax = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  const sliderMax = manualCeiling(activeMax, tdp.on_ac, tdp.manual_max_ac);
  const isAutoOn = !monitorOnly && (power?.auto_tdp ?? false);
  const visualLimits = { ...tdp.limits, min: isAutoOn ? tdp.limits.min : requestMin };
  // Reference watts clamped to the active ceiling; the reset link shows only when
  // the current value differs from it.
  const resetTarget = resetWatts(tdp.limits.default, tdp.limits.min, activeMax);
  // Firmware modes replace the watt presets. In a named mode the firmware owns
  // power+fan, so the arc/slider show its applied watts; the slider drops to custom.
  const fwModes = tdp.firmware_modes ?? [];
  const hasFwModes = fwModes.length > 0;
  const inFwMode = hasFwModes && tdp.firmware_mode !== "custom";
  const shownWatts = inFwMode ? (tdp.applied_w ?? view.watts) : view.watts;
  const zone = isAutoOn || inFwMode ? null : extraZone(shownWatts, tdp.limits.min, activeMax);
  const extraMessage = zone === "low"
    ? t("tdp.extra.low", { min: tdp.limits.min })
    : zone === "high"
      ? t(tdp.extra_needs_accessory ? "tdp.extra.highAccessory" : "tdp.extra.high", { max: activeMax })
      : null;
  const atCeiling = zone === null && Math.min(view.watts, sliderMax) >= sliderMax;
  const ownership = ownershipView(tdp.ownership, tdp.limits.min);
  // In the extra range the dial and the note already say the firmware decides.
  const showOwnership = ownershipMessage(tdp.ownership, tdp.limits.min, tdp.on_ac) !== null
    && !(zone !== null && ["constrained", "rejected", "conflict"].includes(ownership.kind));
  const deckPptActive = Boolean(tdp.ppt?.supported && view.mode !== "estable");
  const arcTarget = deckPptActive ? (tdp.ppt?.requested.slow ?? shownWatts) : shownWatts;
  const arcApplied = deckPptActive
    ? (tdp.ppt?.applied.slow ?? null)
    : (power?.applied ?? (monitorOnly ? tdp.applied_w : null));
  const basePpt = deckPptActive ? shownWatts : null;
  const slowPpt = deckPptActive ? (tdp.ppt?.requested.slow ?? null) : null;
  const fastPpt = deckPptActive ? (tdp.ppt?.requested.fast ?? null) : null;
  const pptVisualMax = deckPptActive ? Math.max(activeMax, slowPpt ?? 0, fastPpt ?? 0) : null;
  const biosNoticeAbove = tdp.ppt?.supported && !tdp.overclock?.detected ? STEAM_DECK_NOMINAL_MAX_W : null;

  const levelUnit = isLevelUnit(tdp.unit);
  const split = levelUnit && Boolean(tdp.gpu_level_supported) && !inFwMode;
  const linked = storedGpu === null;
  const editingGpu = split && target === "gpu" && !linked;
  const autoSetpoint = isAutoOn ? (power?.setpoint ?? null) : null;
  const cpuShown = isAutoOn && autoSetpoint !== null ? autoSetpoint : shownWatts;
  const autoConfig = scope === "global" ? tdp.global_auto_config : tdp.auto_config;
  const gpuShown = linked
    ? cpuShown
    : isAutoOn && autoConfig
      ? autoGpuLevel(storedGpu, view.watts, cpuShown, autoConfig, tdp.auto_limits ?? tdp.limits, tdp.on_ac)
      : Math.max(tdp.limits.min, Math.min(activeMax, storedGpu));
  const frequenciesAt = (level: number) => tdp.level_frequencies?.[String(Math.round(Math.min(level, activeMax)))];
  const levelSummary = !levelUnit
    ? null
    : split && !linked
      ? levelFrequencySummary(frequenciesAt(cpuShown), frequenciesAt(gpuShown), target === "gpu")
      : levelFrequencySummary(frequenciesAt(shownWatts));
  const ghost = split && !linked
    ? (target === "gpu"
      ? { value: cpuShown, label: t("tdp.target.cpu") }
      : { value: gpuShown, label: t("tdp.target.gpu") })
    : null;
  const heroLabel = split ? t(target === "gpu" ? "tdp.target.gpu" : "tdp.target.cpu") : null;
  const dialValue = editingGpu ? gpuShown : shownWatts;
  // On the GPU tab the way back to default is linking the GPU to the CPU level again.
  const showReset = editingGpu || Math.round(view.watts) !== resetTarget;
  const onDial = editingGpu ? (level: number) => onGpuLevel?.(level) : onWatts;
  const onLinked = (next: boolean) => onGpuLevel?.(next ? null : Math.round(view.watts));
  const targetTabs = split ? (
    <PanelSectionRow>
      <PowerTargetTabs
        target={target}
        cpuLevel={Math.round(cpuShown)}
        gpuLevel={Math.round(gpuShown)}
        linked={linked}
        onTarget={setTarget}
        onLinked={onLinked}
      />
    </PanelSectionRow>
  ) : null;

  // Master switch off: keep the live arc, drop every write control.
  if (monitorOnly) {
    return (
      <>
        <PanelSectionRow>
          <TdpMonitorNotice onReactivate={onReactivate} />
        </PanelSectionRow>
        <PanelSectionRow>
          <PowerArc
            watts={arcTarget}
            limits={visualLimits}
            onAc={tdp.on_ac}
            actualWatts={power?.watts ?? null}
            auto={isAutoOn}
            setpoint={power?.setpoint ?? null}
            appliedWatts={arcApplied}
            visualMax={pptVisualMax}
            baseMarkerWatts={basePpt}
            slowMarkerWatts={slowPpt}
            fastMarkerWatts={fastPpt}
            overclocked={tdp.overclock?.detected ?? false}
            unit={tdp.unit}
          />
        </PanelSectionRow>
      </>
    );
  }


  return (
    <>
      {targetTabs}
      <PanelSectionRow>
        <PowerArc
          watts={editingGpu ? gpuShown : arcTarget}
          limits={visualLimits}
          onAc={tdp.on_ac}
          actualWatts={power?.watts ?? null}
          auto={isAutoOn}
          setpoint={isAutoOn && editingGpu ? gpuShown : (power?.setpoint ?? null)}
          appliedWatts={editingGpu ? null : arcApplied}
          visualMax={pptVisualMax}
          baseMarkerWatts={basePpt}
          slowMarkerWatts={slowPpt}
          fastMarkerWatts={fastPpt}
          overclocked={tdp.overclock?.detected ?? false}
          unit={tdp.unit}
          heroLabel={heroLabel}
          ghost={ghost}
          safeMin={deckPptActive ? null : tdp.limits.min}
          safeMax={deckPptActive ? null : activeMax}
          manualMax={deckPptActive ? null : (tdp.manual_max_ac ?? null)}
        />
      </PanelSectionRow>
      {showOwnership && (
        <PanelSectionRow>
          <TdpOwnershipStatus
            ownership={tdp.ownership}
            onAc={tdp.on_ac}
            physicalMin={tdp.limits.min}
          />
        </PanelSectionRow>
      )}
      {!isAutoOn && (
        <>
          <PanelSectionRow>
            <SliderField
              value={Math.min(dialValue, sliderMax)}
              min={requestMin}
              max={sliderMax}
              step={1}
              showValue
              onChange={onDial}
            />
          </PanelSectionRow>
          {levelSummary && (
            <PanelSectionRow>
              <div style={{
                textAlign: "center",
                color: theme.color.textMuted,
                fontSize: theme.font.caption,
                fontVariantNumeric: "tabular-nums",
              }}>
                {levelSummary}
              </div>
            </PanelSectionRow>
          )}
          {!inFwMode && tdp.low_battery_hold?.available && (
            <PanelSectionRow>
              <ToggleField
                label={(
                  <ExperimentalLabel
                    badge={t("tdp.lowBatteryHold.experimental")}
                    title={t("tdp.lowBatteryHold.title")}
                  />
                )}
                description={t("tdp.lowBatteryHold.hint")}
                checked={tdp.low_battery_hold.enabled}
                onChange={onLowBatteryHold}
                bottomSeparator="none"
              />
            </PanelSectionRow>
          )}
          {extraMessage && !levelUnit && (
            <PanelSectionRow>
              <div style={{
                display: "flex",
                alignItems: "flex-start",
                gap: theme.space.xs,
                color: theme.color.textMuted,
                fontSize: theme.font.caption,
              }}>
                <span aria-hidden style={{
                  flexShrink: 0,
                  width: 7,
                  height: 7,
                  marginTop: 4,
                  borderRadius: "50%",
                  background: zone === "low" ? theme.color.extraLow : theme.color.extra,
                }} />
                <span>{extraMessage}</span>
              </div>
            </PanelSectionRow>
          )}
          {atCeiling && !levelUnit && (
            <PanelSectionRow>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {tdp.on_ac
                  ? t("tdp.ceiling.charger", { max: activeMax })
                  : t("tdp.ceiling.battery", { max: activeMax })}
              </div>
            </PanelSectionRow>
          )}
          {hasFwModes ? (
            <>
              <PanelSectionRow>
                <FirmwareModes
                  modes={fwModes}
                  active={tdp.firmware_mode}
                  labels={{
                    "low-power": t("tdp.fwmode.low-power"),
                    balanced: t("tdp.fwmode.balanced"),
                    performance: t("tdp.fwmode.performance"),
                  }}
                  onPick={onFirmwareMode}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: 8 }}>
                  {inFwMode ? t("tdp.fwmode.active") : t("tdp.fwmode.custom")}
                </div>
              </PanelSectionRow>
            </>
          ) : (
            <>
              {editingGpu && gpuResolved ? (
                <PanelSectionRow>
                  <Presets
                    resolved={gpuResolved}
                    manageLabel={t("tdp.presets.manage")}
                    hiddenLabel={t("tdp.presets.hidden")}
                    onPick={(item) => onGpuLevel?.(item.watts)}
                    onEdit={onEditPresets}
                  />
                </PanelSectionRow>
              ) : resolved && (
                <PanelSectionRow>
                  <Presets
                    resolved={resolved}
                    manageLabel={t("tdp.presets.manage")}
                    hiddenLabel={t("tdp.presets.hidden")}
                    onPick={onApplyPreset}
                    onEdit={onEditPresets}
                  />
                </PanelSectionRow>
              )}
              {showReset && (
                <PanelSectionRow>
                  <Focusable
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      padding: "4px 0",
                      marginTop: 4,
                      color: theme.color.textMuted,
                      fontSize: theme.font.caption,
                      cursor: "pointer",
                    }}
                    onActivate={() => (editingGpu ? onGpuLevel?.(null) : onWatts(resetTarget))}
                    onClick={() => (editingGpu ? onGpuLevel?.(null) : onWatts(resetTarget))}
                  >
                    {editingGpu
                      ? t("tdp.target.link")
                      : levelUnit
                        ? t("tdp.reset.default.level", { w: resetTarget })
                        : t("tdp.reset.default", { w: resetTarget })}
                  </Focusable>
                </PanelSectionRow>
              )}
            </>
          )}
          {!inFwMode && tdp.supports_advanced && (
            <PanelSectionRow>
              <AdvancedBoost
                levels={view.levels}
                mode={view.mode}
                bounds={{ pl2: tdp.level_limits.pl2, pl3: tdp.level_limits.pl3 }}
                ppt={tdp.ppt}
                biosNoticeAbove={biosNoticeAbove}
                onSetLevels={onSetLevels}
                onSetMode={onSetMode}
              />
            </PanelSectionRow>
          )}
          {/* Learned-band suggestion: apply a FIXED watt value the loop has learned
              this game lives in. Auto OFF only (it's a third, distinct way to set TDP:
              manual slider · auto-TDP dynamic · learned fixed). Renders nothing without
              an enough band (never a fabricated suggestion). */}
          {!inFwMode && tdp.learned.enough && (
            <PanelSectionRow>
              <TdpSuggestionCard learned={tdp.learned} onApply={onApplySuggestion} />
            </PanelSectionRow>
          )}
        </>
      )}
    </>
  );
};
