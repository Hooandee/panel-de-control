import { FC } from "react";
import { ToggleField } from "@decky/ui";

import { CpuState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { activeThreads, formatGhz, threadsPerCore, turboFraction } from "../system/cpu";

interface Props {
  state: CpuState;
  onSetSmt: (enabled: boolean) => void;
  onSetBoost: (enabled: boolean) => void;
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

export const CpuCard: FC<Props> = ({ state, onSetSmt, onSetBoost }) => {
  const { t } = useI18n();
  const smtOn = state.smt.enabled;
  const boostOn = state.boost.enabled;
  const cores = state.cores;
  const tpc = threadsPerCore(state.cores, state.threads);
  const turbo = turboFraction(state.base_khz, state.max_khz);
  const peak = boostOn ? state.max_khz : state.base_khz;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
      {/* Identity */}
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{state.chip}</div>

      {/* Cores × threads */}
      {cores !== null && cores > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", gap: 3 }}>
            {Array.from({ length: cores }, (_, i) => (
              <Core key={i} pips={tpc} lit={smtOn ? tpc : 1} />
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

      {/* Controls */}
      {state.smt.supported && (
        <ToggleField
          label={t("system.cpu.smt")}
          description={t("system.cpu.smt.desc")}
          checked={smtOn}
          onChange={onSetSmt}
        />
      )}
      {state.boost.supported && (
        <ToggleField
          label={t("system.cpu.boost")}
          description={t("system.cpu.boost.desc")}
          checked={boostOn}
          onChange={onSetBoost}
        />
      )}
    </div>
  );
};
