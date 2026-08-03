import { FC } from "react";
import { ToggleField } from "@decky/ui";

import { CpuState, TdpScope } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { activeThreads, clampCpuWindow, formatCpuFrequency, formatGhz, threadsPerCore, turboFraction } from "../system/cpu";
import { ContainedSlider } from "./ContainedSlider";
import { ProfileSelector } from "./ProfileSelector";

interface Props {
  state: CpuState;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  onScope: (s: TdpScope) => void;
  onSetSmt: (enabled: boolean) => void;
  onSetBoost: (enabled: boolean) => void;
  onSetCores: (count: number) => void;
  onSetFrequencyManual: (manual: boolean) => void;
  onSetFrequency: (minimumKhz: number, maximumKhz: number) => void;
}

// Boost-off turbo tail: dim but visible, so "boost off" reads differently from
// "no turbo headroom at all".
const TURBO_OFF = "rgba(255,138,61,0.28)";

/** A physical core drawn as `pips` thread slots; the first `lit` are active. */
const Core: FC<{ pips: number; lit: number }> = ({ pips, lit }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: "1 1 0", minWidth: 6 }}>
    {Array.from({ length: pips }, (_, i) => (
      <div key={i} style={{ height: 6, borderRadius: 2, background: i < lit ? theme.color.accent : theme.color.hairline }} />
    ))}
  </div>
);

export const CpuCard: FC<Props> = ({
  state,
  scope,
  game,
  onScope,
  onSetSmt,
  onSetBoost,
  onSetCores,
  onSetFrequencyManual,
  onSetFrequency,
}) => {
  const { t, lang } = useI18n();
  const smtOn = state.smt.enabled;
  const boostOn = state.boost.enabled;
  const cores = state.cores;
  const tpc = threadsPerCore(state.cores, state.threads);
  const turbo = turboFraction(state.base_khz, state.max_khz);
  const peak = boostOn ? state.max_khz : state.base_khz;
  // How many physical cores are active (for both the pip viz and the slider).
  const activeCores = state.active_cores ?? cores ?? 0;
  const frequency = state.frequency;
  const frequencyMin = frequency.requested_min_khz ?? frequency.applied_min_khz ?? frequency.range_min_khz;
  const frequencyMax = frequency.requested_max_khz ?? frequency.applied_max_khz ?? frequency.range_max_khz;
  const frequencyAdapted = frequency.status === "clamped" || frequency.policy_state.some(
    (policy) => policy.applied_min_khz !== frequency.applied_min_khz || policy.applied_max_khz !== frequency.applied_max_khz,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
      {/* Per-game scope: only shown in-game (one tab governs SMT/boost/cores together). */}
      {game && (
        <ProfileSelector
          scope={scope}
          gameName={game.name}
          hasGameProfile={state.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("tdp.inherit")}
          onScope={onScope}
        />
      )}
      {/* Identity */}
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{state.chip}</div>

      {/* Cores × threads */}
      {cores !== null && cores > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", gap: 3 }}>
            {Array.from({ length: cores }, (_, i) => (
              <Core key={i} pips={tpc} lit={i < activeCores ? (smtOn ? tpc : 1) : 0} />
            ))}
          </div>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("system.cpu.threads", { cores, threads: activeThreads(cores, state.threads ?? cores, smtOn) })}
          </div>
        </div>
      )}

      {/* Frequency base → turbo */}
      {state.max_khz !== null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("system.cpu.frequency")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{formatGhz(peak)}</span>
          </div>
          <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: theme.color.hairline }}>
            <div style={{ flex: `${1 - turbo} 0 0`, background: theme.color.accent }} />
            {turbo > 0 && (
              <div style={{ flex: `${turbo} 0 0`, background: boostOn ? theme.color.boost : TURBO_OFF }} />
            )}
          </div>
        </div>
      )}

      {/* Active core count */}
      {state.cores_supported && state.max_cores !== null && state.max_cores > 1 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("system.cpu.activeCores")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{activeCores} / {state.max_cores}</span>
          </div>
          <ContainedSlider
            value={activeCores}
            min={1}
            max={state.max_cores}
            step={1}
            onChange={onSetCores}
          />
        </div>
      )}

      {frequency.supported
        && frequency.range_min_khz !== null
        && frequency.range_max_khz !== null
        && frequencyMin !== null
        && frequencyMax !== null && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <ToggleField
            label={t("system.cpu.frequency.manual")}
            description={t("system.cpu.frequency.manual.desc")}
            checked={frequency.manual}
            onChange={onSetFrequencyManual}
            bottomSeparator="none"
          />
          {frequency.manual && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
                <span>{t("system.cpu.frequency.min")}</span>
                <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{formatCpuFrequency(frequencyMin, lang)}</span>
              </div>
              <ContainedSlider
                value={frequencyMin}
                min={frequency.range_min_khz}
                max={frequency.range_max_khz}
                step={100_000}
                onChange={(value) => {
                  const [minimum, maximum] = clampCpuWindow(value, frequencyMax, frequency.range_min_khz!, frequency.range_max_khz!);
                  onSetFrequency(minimum, maximum);
                }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
                <span>{t("system.cpu.frequency.max")}</span>
                <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{formatCpuFrequency(frequencyMax, lang)}</span>
              </div>
              <ContainedSlider
                value={frequencyMax}
                min={frequency.range_min_khz}
                max={frequency.range_max_khz}
                step={100_000}
                onChange={(value) => onSetFrequency(frequencyMin, Math.max(value, frequencyMin))}
              />
              {frequencyAdapted && (
                <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                  {t("system.cpu.frequency.adapted")}
                </div>
              )}
              {(frequency.status === "failed" || frequency.status === "partial") && (
                <div style={{ fontSize: theme.font.caption, color: theme.color.danger }}>
                  {t("system.cpu.frequency.rejected")}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Controls */}
      {state.smt.supported && (
        <ToggleField
          label={t("system.cpu.smt")}
          description={t("system.cpu.smt.desc")}
          checked={smtOn}
          onChange={onSetSmt}
          bottomSeparator="none"
        />
      )}
      {state.boost.supported && (
        <ToggleField
          label={t("system.cpu.boost")}
          description={t("system.cpu.boost.desc")}
          checked={boostOn}
          onChange={onSetBoost}
          bottomSeparator="none"
        />
      )}
    </div>
  );
};
