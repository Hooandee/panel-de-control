import { PanelSectionRow, SliderField, Focusable } from "@decky/ui";
import { FC, useCallback, useMemo } from "react";

import { TdpState, TdpScope, PowerDraw, BoostMode, PowerPresetState } from "../api";
import { resetWatts, offsetOf } from "../tdp/logic";
import { resolveItems, PresetItem, BUILTIN_IDS } from "../tdp/powerPresets";
import { openPowerPresetsModal } from "./PowerPresetsModal";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";
import { FirmwareModes } from "./FirmwareModes";
import { AdvancedBoost } from "./AdvancedBoost";
import { TdpSuggestionCard } from "./TdpSuggestionCard";
import { TdpMonitorNotice } from "./TdpMonitorNotice";

// Learned-band reasons worth surfacing as "still learning" (others — no_game,
// disabled, error — show no line).
const LEARNING_REASONS = new Set(["no_data", "too_few", "one_level"]);

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  power: PowerDraw | null;
  onScope: (scope: TdpScope) => void;
  onWatts: (watts: number) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onSetMode: (mode: BoostMode) => void;
  // Apply the learned-band suggestion as a FIXED PL1 (also turns auto-TDP off).
  onApplySuggestion: (watts: number) => void;
  // Select a firmware performance mode (Legion Go original); "custom" via the slider.
  onFirmwareMode: (mode: string) => void;
  // Master switch off: show only the live arc + a notice, hide write controls.
  monitorOnly?: boolean;
  // Flip the master switch back on from the monitor notice.
  onReactivate?: () => void;
  // Custom power-preset library (built-in watts resolved from `tdp.presets`).
  presets: PowerPresetState | null;
  refreshPresets: () => void;
  onApplyPreset: (item: PresetItem) => void;
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, power, onScope, onWatts, onSetLevels, onSetMode, onApplySuggestion, onFirmwareMode, monitorOnly, onReactivate, presets, refreshPresets, onApplyPreset }) => {
  const { t } = useI18n();

  // Memoized (and above the early returns) so re-renders don't rebuild the chip list.
  // Falls back to a builtins-only library if the custom library hasn't loaded.
  const resolved = useMemo(() => {
    if (!tdp) return null;
    const lib = presets ?? { order: [...BUILTIN_IDS], hidden: [], custom: {} };
    const ceiling = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
    const w = scope === "global" ? tdp.global_watts : tdp.watts;
    const lv = scope === "global" ? tdp.global_levels : tdp.levels;
    const mode = scope === "global" ? tdp.global_boost_mode : tdp.boost_mode;
    const liveBoost = { mode, off2: offsetOf(lv.pl2, lv.pl1), off3: offsetOf(lv.pl3, lv.pl2) };
    return resolveItems(lib, tdp.presets, tdp.on_ac, w, ceiling, liveBoost);
  }, [tdp, presets, scope]);

  // Stable identity so the memoized chip row doesn't re-render on every tick. Edit range is
  // the charger ceiling so a charger-made preset isn't clipped when edited on battery.
  const onEditPresets = useCallback(() => {
    if (!tdp) return;
    openPowerPresetsModal({
      builtinWatts: tdp.presets,
      onAc: tdp.on_ac,
      currentWatts: scope === "global" ? tdp.global_watts : tdp.watts,
      min: tdp.limits.min,
      max: tdp.limits.max_ac,
      supportsAdvanced: tdp.supports_advanced,
      // Absolute rail ceilings; the editor bounds each margin against the preset's own PL1
      // so a rail can never exceed its firmware max.
      pl2Max: tdp.level_limits.pl2?.max ?? tdp.limits.max_ac,
      pl3Max: tdp.level_limits.pl3?.max ?? tdp.limits.max_ac,
      onClose: refreshPresets,
    });
  }, [tdp, scope, refreshPresets]);

  if (!tdp) return <Loading />;

  if (!tdp.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  }

  const view =
    scope === "global"
      ? { watts: tdp.global_watts, levels: tdp.global_levels, mode: tdp.global_boost_mode }
      : { watts: tdp.watts, levels: tdp.levels, mode: tdp.boost_mode };
  // Active ceiling: on battery the device-aware cap (max), on charger max_ac.
  // Never offer more than the current power source can deliver.
  const activeMax = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  const isAutoOn = power?.auto_tdp ?? false;
  const atCeiling = Math.min(view.watts, activeMax) >= activeMax;
  // Reference watts clamped to the active ceiling; the reset link shows only when
  // the current value differs from it.
  const resetTarget = resetWatts(tdp.limits.default, tdp.limits.min, activeMax);
  const showReset = Math.round(view.watts) !== resetTarget;
  // Firmware modes replace the watt presets. In a named mode the firmware owns
  // power+fan, so the arc/slider show its applied watts; the slider drops to custom.
  const fwModes = tdp.firmware_modes ?? [];
  const hasFwModes = fwModes.length > 0;
  const inFwMode = hasFwModes && tdp.firmware_mode !== "custom";
  const shownWatts = inFwMode ? (tdp.applied_w ?? view.watts) : view.watts;

  // Master switch off: keep the live arc, drop every write control.
  if (monitorOnly) {
    return (
      <>
        <PanelSectionRow>
          <TdpMonitorNotice onReactivate={onReactivate} />
        </PanelSectionRow>
        <PanelSectionRow>
          <PowerArc
            watts={shownWatts}
            limits={tdp.limits}
            onAc={tdp.on_ac}
            actualWatts={power?.watts ?? null}
            gpuBusy={power?.gpu_busy ?? null}
            auto={isAutoOn}
            setpoint={power?.setpoint ?? null}
            appliedWatts={power?.applied ?? null}
          />
        </PanelSectionRow>
      </>
    );
  }

  return (
    <>
      {/* Hidden under a firmware mode: it owns the rails, so a per-game TDP scope has
          no effect there (same as the advanced/boost controls below). */}
      {!inFwMode && (
        <PanelSectionRow>
          <ProfileSelector
            scope={scope}
            gameName={game?.name ?? null}
            hasGameProfile={tdp.has_game_profile}
            globalLabel={t("tdp.scope.global")}
            inheritHint={t("tdp.inherit")}
            onScope={onScope}
          />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <PowerArc
          watts={shownWatts}
          limits={tdp.limits}
          onAc={tdp.on_ac}
          actualWatts={power?.watts ?? null}
          gpuBusy={power?.gpu_busy ?? null}
          auto={isAutoOn}
          setpoint={power?.setpoint ?? null}
          appliedWatts={power?.applied ?? null}
        />
      </PanelSectionRow>
      {tdp.external_change && (
        // An external tool moved the TDP and we adopted it — say so, so the value
        // doesn't read as a bug.
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.external_change")}
          </div>
        </PanelSectionRow>
      )}
      {/* Auto status, sitting directly under the arc so it fills what would
          otherwise be dead space above the toggle. */}
      {isAutoOn && power?.ui_floor_engaged && (
        // Honest: opening the QAM raised PL1 so the CPU-bound menu render stays
        // fluid — the arc shows a menu-temporary value, NOT the settled in-game one.
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.auto.ui_floor")}
          </div>
        </PanelSectionRow>
      )}
      {isAutoOn && (
        // The learned band when ready, a plain "learning…" note while collecting,
        // nothing otherwise. Auto-TDP itself is decoupled from the band (runs the
        // full range + explores); this is a read-only status line.
        tdp.learned.enough ? (
          <PanelSectionRow>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("tdp.learned.band", { lo: tdp.learned.floor!, hi: tdp.learned.ceil! })}
            </div>
          </PanelSectionRow>
        ) : LEARNING_REASONS.has(tdp.learned.reason) ? (
          <PanelSectionRow>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("tdp.learned.learning.title")}
            </div>
          </PanelSectionRow>
        ) : null
      )}
      {!isAutoOn && (
        <>
          <PanelSectionRow>
            <SliderField
              value={Math.min(shownWatts, activeMax)}
              min={tdp.limits.min}
              max={activeMax}
              step={1}
              showValue
              onChange={onWatts}
            />
          </PanelSectionRow>
          {atCeiling && (
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
              {resolved && (
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
                    onActivate={() => onWatts(resetTarget)}
                    onClick={() => onWatts(resetTarget)}
                  >
                    {t("tdp.reset.default", { w: resetTarget })}
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
