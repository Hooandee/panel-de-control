import { useCallback, useEffect, useRef, useState } from "react";
import {
  CpuState,
  TdpScope,
  getCpuState,
  setActiveCores,
  setCpuBoost,
  setCpuFollowGlobal,
  setCpuFrequency,
  setCpuFrequencyAuto,
  setSmt,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";

const POLL_MS = 3000; // topology/freq change rarely

export interface CpuController {
  state: CpuState | null;
  scope: TdpScope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (s: TdpScope) => void;
  setSmt: (enabled: boolean) => void;
  setBoost: (enabled: boolean) => void;
  setCores: (count: number) => void;
  setFrequencyManual: (manual: boolean) => void;
  setFrequency: (minimumKhz: number, maximumKhz: number) => void;
}

/**
 * Polls get_cpu_state() every ~3 s while mounted. SMT/boost setters are optimistic
 * (flip the toggle immediately) with a pending guard so an in-flight write isn't
 * clobbered by a poll landing mid-flight. Never throws.
 */
export function useCpu(): CpuController {
  const game = useRunningGame();
  const [state, setState] = useState<CpuState | null>(null);
  const pending = useRef(false);
  const frequencyQueued = useRef(false);
  const frequencyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appid = game?.appid;

  const cancelQueuedFrequency = useCallback(() => {
    if (frequencyTimer.current !== null) {
      clearTimeout(frequencyTimer.current);
      frequencyTimer.current = null;
    }
    frequencyQueued.current = false;
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getCpuState()
        .then((s) => {
          if (alive && !pending.current && !frequencyQueued.current) setState(s);
        })
        .catch(() => {
          /* keep last values */
        });
    };
    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
      cancelQueuedFrequency();
    };
  }, [appid, cancelQueuedFrequency]);

  // The card's tab reflects the game's active profile and IS the control (shared wiring).
  // The pending guard stops a poll landing mid-write from clobbering the optimistic state.
  const applyFollow = useCallback((f: boolean, a: string) => {
    pending.current = true;
    setCpuFollowGlobal(f, a).then(setState).catch(() => {}).finally(() => { pending.current = false; });
  }, []);
  const { scope, onScope: syncScope } = useScopeSync(
    appid, state?.follows_global, applyFollow,
  );
  const onScope = useCallback((next: TdpScope) => {
    cancelQueuedFrequency();
    syncScope(next);
  }, [cancelQueuedFrequency, syncScope]);

  const target = scope === "game" ? (appid ?? null) : null;

  const apply = useCallback(
    (optimistic: (s: CpuState) => CpuState, rpc: () => Promise<CpuState>) => {
      setState((prev) => (prev ? optimistic(prev) : prev));
      pending.current = true;
      rpc()
        .then((s) => setState(s))
        .catch(() => getCpuState().then(setState).catch(() => {}))
        .finally(() => {
          pending.current = false;
        });
    },
    [],
  );

  const doSmt = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, smt: { ...s.smt, enabled } }), () => setSmt(enabled, scope, target)),
    [apply, scope, target],
  );
  const doBoost = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, boost: { ...s.boost, enabled } }), () => setCpuBoost(enabled, scope, target)),
    [apply, scope, target],
  );
  const doCores = useCallback(
    (count: number) =>
      apply((s) => ({ ...s, active_cores: count }), () => setActiveCores(count, scope, target)),
    [apply, scope, target],
  );

  const doFrequency = useCallback(
    (minimumKhz: number, maximumKhz: number) => {
      setState((previous) => previous ? {
        ...previous,
        frequency: {
          ...previous.frequency,
          manual: true,
          requested_min_khz: minimumKhz,
          requested_max_khz: maximumKhz,
          status: "configured",
        },
      } : previous);
      cancelQueuedFrequency();
      frequencyQueued.current = true;
      frequencyTimer.current = setTimeout(() => {
        frequencyTimer.current = null;
        frequencyQueued.current = false;
        pending.current = true;
        setCpuFrequency(minimumKhz, maximumKhz, scope, target)
          .then(setState)
          .catch(() => getCpuState().then(setState).catch(() => {}))
          .finally(() => { pending.current = false; });
      }, 200);
    },
    [cancelQueuedFrequency, scope, target],
  );

  const doFrequencyManual = useCallback(
    (manual: boolean) => {
      cancelQueuedFrequency();
      if (!manual) {
        apply(
          (s) => ({ ...s, frequency: { ...s.frequency, manual: false, status: "automatic" } }),
          () => setCpuFrequencyAuto(scope, target),
        );
        return;
      }
      const frequency = state?.frequency;
      const minimum = frequency?.requested_min_khz ?? frequency?.applied_min_khz ?? frequency?.range_min_khz;
      const maximum = frequency?.requested_max_khz ?? frequency?.applied_max_khz ?? frequency?.range_max_khz;
      if (minimum !== null && minimum !== undefined && maximum !== null && maximum !== undefined) {
        apply(
          (s) => ({ ...s, frequency: { ...s.frequency, manual: true, status: "configured" } }),
          () => setCpuFrequency(minimum, maximum, scope, target),
        );
      }
    },
    [apply, cancelQueuedFrequency, scope, state?.frequency, target],
  );

  return {
    state,
    scope,
    game,
    onScope,
    setSmt: doSmt,
    setBoost: doBoost,
    setCores: doCores,
    setFrequencyManual: doFrequencyManual,
    setFrequency: doFrequency,
  };
}
