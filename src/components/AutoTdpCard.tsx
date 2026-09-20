import { FC } from "react";
import { PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { LuGauge, LuTarget } from "react-icons/lu";

import { AutoTdpConfig, AutoTdpLive, TdpLimits, TdpScope } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { effectiveAutoRange } from "../tdp/autoView";

const MIN_TARGET_FPS = 20;
const MAX_TARGET_FPS = 240;

interface Props {
  config: AutoTdpConfig;
  scope: TdpScope;
  limits: TdpLimits;
  requestLimits: TdpLimits;
  onAc: boolean;
  maxTargetFps?: number | null;
  live: AutoTdpLive | null;
  liveApplies: boolean;
  onToggle: (enabled: boolean) => void;
  onTargetFps: (fps: number) => void;
  onInitialTdp: (watts: number) => void;
  onMinTdp: (watts: number) => void;
  onMaxTdp: (watts: number) => void;
}

function statusKey(live: AutoTdpLive): string {
  if (live.reason === "awaiting_gameplay") {
    return "tdp.auto.status.awaiting_gameplay";
  }
  if (live.reason === "load_shift") {
    return "tdp.auto.status.load_shift";
  }
  if (live.state !== "paused") return `tdp.auto.status.${live.state}`;
  if (
    live.reason === "ui_active"
    || live.reason === "no_game_focus"
  ) {
    return live.held_watts === null
      ? "tdp.auto.status.paused_menu_stable"
      : "tdp.auto.status.paused_menu";
  }
  if (live.reason === "fps_stale" || live.reason === "fps_unavailable") {
    return "tdp.auto.status.paused_signal";
  }
  if (
    live.reason === "external_owner"
    || live.reason === "tdp_unsupported"
    || live.reason === "control_disabled"
    || live.reason === "apply_unconfirmed"
    || live.reason === "apply_failed"
    || live.reason === "apply_retry_wait"
  ) {
    return "tdp.auto.status.paused_control";
  }
  return "tdp.auto.status.paused";
}

export const AutoTdpCard: FC<Props> = ({
  config,
  scope,
  limits,
  requestLimits,
  onAc,
  maxTargetFps,
  live,
  liveApplies,
  onToggle,
  onTargetFps,
  onInitialTdp,
  onMinTdp,
  onMaxTdp,
}) => {
  const { t } = useI18n();
  const scopeLabel = scope === "global"
    ? t("tdp.auto.scope.global")
    : t("tdp.scope.game");
  const targetCeiling = Math.max(
    MIN_TARGET_FPS,
    Math.min(maxTargetFps ?? MAX_TARGET_FPS, MAX_TARGET_FPS),
  );
  const targetFps = Math.max(
    MIN_TARGET_FPS,
    Math.min(config.target_fps, targetCeiling),
  );
  const showLive = config.enabled && liveApplies && live !== null;
  const selectedMin = config.min_tdp ?? requestLimits.min;
  const selectedMax = config.max_tdp ?? requestLimits.max_ac;
  const range = effectiveAutoRange(config, limits, onAc);
  const constrained = range.min !== selectedMin || range.max !== selectedMax;
  const initialTdp = Math.max(range.min, Math.min(config.initial_tdp, range.max));
  const shownFps = live?.fps == null ? null : Math.round(live.fps);
  const menuPaused = live?.state === "paused" && (
    live.reason === "ui_active"
    || live.reason === "no_game_focus"
  );
  const maintainedWatts = live?.held_watts ?? live?.setpoint ?? config.initial_tdp;
  const statusValues: Record<string, string | number> = live?.state === "holding"
    || live?.state === "optimizing"
    || live?.state === "recovering"
    ? {
        fps: shownFps ?? config.target_fps,
        watts: maintainedWatts,
      }
    : menuPaused && live?.held_watts === null
    ? {}
    : { watts: maintainedWatts };

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, marginBottom: theme.space.card }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, marginBottom: theme.space.sm }}>
          <LuGauge size={18} color={theme.color.accent} aria-hidden />
          <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", flexWrap: "wrap", gap: theme.space.xs }}>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>
              {t("tdp.auto.title")}
            </span>
            <span style={{
              padding: "1px 5px",
              borderRadius: 999,
              color: theme.color.warn,
              boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
              fontSize: 10,
              fontWeight: 700,
              flexShrink: 0,
            }}>
              {t("tdp.auto.experimental")}
            </span>
          </div>
          <div style={{
            padding: "2px 7px",
            borderRadius: 999,
            color: theme.color.accent,
            background: `rgba(${theme.color.accentRgb}, 0.12)`,
            fontSize: theme.font.caption,
            fontWeight: 700,
            flexShrink: 0,
          }}>
            {scopeLabel}
          </div>
        </div>

        <ToggleField
          label={t("tdp.auto.toggle")}
          description={t("tdp.auto.hint")}
          checked={config.enabled}
          onChange={onToggle}
          bottomSeparator="none"
        />

        {config.enabled && (
          <>
            <div style={{ minWidth: 0, overflow: "hidden", marginTop: theme.space.xs }}>
              <SliderField
                label={t("tdp.auto.target.label")}
                description={t("tdp.auto.target.hint")}
                layout="below"
                value={targetFps}
                min={MIN_TARGET_FPS}
                max={targetCeiling}
                step={1}
                showValue
                editableValue
                validValues="steps"
                minimumDpadGranularity={1}
                valueSuffix=" FPS"
                className="pdc-contained-slider"
                onChange={onTargetFps}
                bottomSeparator="none"
              />
            </div>

            <div style={{
              minWidth: 0,
              overflow: "hidden",
              marginTop: theme.space.sm,
              padding: theme.space.sm,
              borderRadius: theme.radius.sm,
              background: theme.color.surface,
            }}>
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, fontWeight: 700 }}>
                {t("tdp.auto.range.title")}
              </div>
              <SliderField
                label={t("tdp.auto.range.min")}
                layout="below"
                value={selectedMin}
                min={requestLimits.min}
                max={requestLimits.max_ac}
                step={1}
                showValue
                editableValue
                validValues="steps"
                minimumDpadGranularity={1}
                valueSuffix=" W"
                className="pdc-contained-slider"
                onChange={onMinTdp}
                bottomSeparator="none"
              />
              <SliderField
                label={t("tdp.auto.range.max")}
                layout="below"
                value={selectedMax}
                min={requestLimits.min}
                max={requestLimits.max_ac}
                step={1}
                showValue
                editableValue
                validValues="steps"
                minimumDpadGranularity={1}
                valueSuffix=" W"
                className="pdc-contained-slider"
                onChange={onMaxTdp}
                bottomSeparator="none"
              />
              {constrained && (
                <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
                  {t("tdp.auto.range.constrained", { min: range.min, max: range.max })}
                </div>
              )}
            </div>

            <div style={{ minWidth: 0, overflow: "hidden", marginTop: theme.space.xs }}>
              <SliderField
                label={t("tdp.auto.initial.label")}
                layout="below"
                value={initialTdp}
                min={range.min}
                max={range.max}
                step={1}
                showValue
                editableValue
                validValues="steps"
                minimumDpadGranularity={1}
                valueSuffix=" W"
                className="pdc-contained-slider"
                onChange={onInitialTdp}
                bottomSeparator="none"
              />
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
                {t("tdp.auto.initial.hint")}
              </div>
            </div>

            <div style={{
              display: "flex",
              alignItems: "center",
              gap: theme.space.xs,
              marginTop: theme.space.sm,
              padding: `${theme.space.sm}px ${theme.space.sm}px`,
              borderRadius: theme.radius.sm,
              background: `rgba(${theme.color.accentRgb}, 0.08)`,
              color: theme.color.textMuted,
              fontSize: theme.font.caption,
            }}>
              <LuTarget size={14} color={theme.color.accent} style={{ flexShrink: 0 }} aria-hidden />
              <span style={{ minWidth: 0, lineHeight: 1.35 }}>
                {showLive && live !== null
                  ? t(statusKey(live), statusValues)
                  : t("tdp.auto.status.waiting_game")}
              </span>
            </div>
            {showLive && live?.seed_source === "learned" && live.seed_watts != null
              && live.target_fps === config.target_fps && (
              <div style={{ marginTop: theme.space.xs, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
                {t("tdp.auto.learned_start", { watts: live.seed_watts, fps: config.target_fps })}
              </div>
            )}
          </>
        )}
      </div>
    </PanelSectionRow>
  );
};
