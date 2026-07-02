import { useCallback, useEffect, useRef, useState } from "react";
import { CpuState, getCpuState, setCpuBoost, setSmt } from "../api";

const POLL_MS = 3000; // topology/freq change rarely

export interface CpuController {
  state: CpuState | null;
  setSmt: (enabled: boolean) => void;
  setBoost: (enabled: boolean) => void;
}

/**
 * Polls get_cpu_state() every ~3 s while mounted. SMT/boost setters are optimistic
 * (flip the toggle immediately) with a pending guard so an in-flight write isn't
 * clobbered by a poll landing mid-flight. Never throws.
 */
export function useCpu(): CpuController {
  const [state, setState] = useState<CpuState | null>(null);
  const pending = useRef(false);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getCpuState()
        .then((s) => {
          if (alive && !pending.current) setState(s);
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
    };
  }, []);

  const apply = useCallback(
    (optimistic: (s: CpuState) => CpuState, rpc: () => Promise<CpuState>) => {
      setState((prev) => (prev ? optimistic(prev) : prev));
      pending.current = true;
      rpc()
        .then((s) => setState(s))
        .catch(() => {
          /* next poll corrects */
        })
        .finally(() => {
          pending.current = false;
        });
    },
    [],
  );

  const doSmt = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, smt: { ...s.smt, enabled } }), () => setSmt(enabled)),
    [apply],
  );
  const doBoost = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, boost: { ...s.boost, enabled } }), () => setCpuBoost(enabled)),
    [apply],
  );

  return { state, setSmt: doSmt, setBoost: doBoost };
}
