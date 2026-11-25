import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import {
  getGpuClock,
  setGpuClock,
  setGpuClockAuto,
  GpuClockState,
  GamePowerOwnerState,
  TdpScope,
} from "../api";
import { subscribePowerOwnershipChanged } from "../tdp/powerOwnershipInvalidation";
import { useRunningGame } from "../tdp/useRunningGame";
import { useGamePowerChangeGuard } from "../tdp/confirmGamePowerChange";

export interface GpuClockControl {
  state: GpuClockState | null;
  scope: TdpScope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (scope: TdpScope) => void;
  setManual: (manual: boolean) => void;
  setWindow: (min: number, max: number) => void;
}

/**
 * Owns the GPU-clock state. Loads once on mount; the min/max sliders commit with a
 * 200 ms debounce (optimistic local update); the Auto/Manual toggle is discrete
 * (returned state is source of truth). Never throws.
 */
export function useGpuClock(): GpuClockControl {
  const game = useRunningGame();
  const appid = game?.appid ?? null;
  const [state, setGpuState] = useState<GpuClockState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestOwner = useRef<GamePowerOwnerState | undefined>(undefined);
  const ownershipRefreshEpoch = useRef(0);
  const editEpoch = useRef(0);
  const setState = useCallback((update: SetStateAction<GpuClockState | null>) => {
    setGpuState((current) => {
      const next = typeof update === "function" ? update(current) : update;
      const owner = latestOwner.current;
      const incoming = next?.game_power_owner;
      if (owner && incoming?.context_appid === owner.context_appid && incoming.revision < owner.revision) {
        return { ...next!, game_power_owner: owner };
      }
      if (incoming) latestOwner.current = incoming;
      return next;
    });
  }, []);
  const stateRef = useRef<GpuClockState | null>(null);
  const confirmedRef = useRef<GpuClockState | null>(null);
  const requestEpoch = useRef(0);
  const mutationPending = useRef(false);
  const contextAppid = useRef(appid);
  const accept = useCallback((next: GpuClockState) => {
    const owner = latestOwner.current;
    if (owner && next.game_power_owner?.context_appid === owner.context_appid
      && next.game_power_owner.revision < owner.revision) next = { ...next, game_power_owner: owner };
    confirmedRef.current = next;
    setState(next);
  }, []);
  const mutate = useCallback(async (request: () => Promise<GpuClockState>) => {
    const epoch = ++requestEpoch.current;
    mutationPending.current = true;
    try {
      const next = await request();
      if (epoch !== requestEpoch.current) return null;
      accept(next);
      return next;
    } catch {
      if (epoch !== requestEpoch.current) return null;
      setState(confirmedRef.current);
      try {
        const next = await getGpuClock();
        if (epoch !== requestEpoch.current) return null;
        accept(next);
        return next;
      } catch {
        return null;
      }
    } finally {
      if (epoch === requestEpoch.current) mutationPending.current = false;
    }
  }, [accept]);
  const [view, setView] = useState<{ appid: string | null; scope: TdpScope | null }>({ appid, scope: null });
  useEffect(() => {
    setView((current) => current.appid === appid ? current : { appid, scope: null });
  }, [appid]);
  const initialScope: TdpScope = appid && state?.appid === appid && !state.follows_global ? "game" : "global";
  const scope = appid && view.appid === appid ? view.scope ?? initialScope : "global";
  const onScope = useCallback((next: TdpScope) => {
    if (commit.current) clearTimeout(commit.current);
    commit.current = null;
    setView({ appid, scope: appid ? next : "global" });
  }, [appid]);
  const shown = state && scope === "global" && state.global_manual !== undefined
    ? { ...state, manual: state.global_manual, min: state.global_min ?? null, max: state.global_max ?? null }
    : state;
  stateRef.current = shown;
  const target = scope === "game" ? appid : null;

  // Re-fetch when the active scope changes so the card shows that scope's window.
  useEffect(() => {
    const contextChanged = contextAppid.current !== appid;
    contextAppid.current = appid;
    if (mutationPending.current && !contextChanged) {
      return () => {
        if (commit.current) clearTimeout(commit.current);
      };
    }
    if (contextChanged) mutationPending.current = false;
    let alive = true;
    const epoch = ++requestEpoch.current;
    const ownershipEpoch = ownershipRefreshEpoch.current;
    getGpuClock()
      .then((next) => {
        if (alive && epoch === requestEpoch.current && ownershipEpoch === ownershipRefreshEpoch.current) accept(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (commit.current) clearTimeout(commit.current);
    };
  }, [scope, appid, accept]);

  useEffect(() => {
    let alive = true;
    const unsubscribe = subscribePowerOwnershipChanged((owner) => {
      if (owner.context_appid !== appid || (latestOwner.current?.context_appid === appid
        && latestOwner.current.revision > owner.revision)) return;
      latestOwner.current = owner;
      const ownershipEpoch = ++ownershipRefreshEpoch.current;
      const intentEpoch = editEpoch.current;
      setState((current) => current ? { ...current, game_power_owner: owner } : current);
      const epoch = requestEpoch.current;
      const pendingEdit = !!commit.current || mutationPending.current;
      getGpuClock().then((next) => {
        if (!alive || contextAppid.current !== appid || epoch !== requestEpoch.current
          || ownershipEpoch !== ownershipRefreshEpoch.current || next.game_power_owner?.context_appid !== appid
          || next.game_power_owner.revision < owner.revision
          || (latestOwner.current?.context_appid === owner.context_appid
            && latestOwner.current.revision > next.game_power_owner.revision)) return;
        if (!pendingEdit && editEpoch.current === intentEpoch && !commit.current && !mutationPending.current) accept(next);
        else setState((current) => current ? { ...current, game_power_owner: next.game_power_owner,
          steam_readback_available: next.steam_readback_available } : current);
      }).catch(() => {});
    });
    return () => { alive = false; unsubscribe(); };
  }, [appid, accept]);

  const setManual = useCallback((manual: boolean) => {
    editEpoch.current += 1;
    if (!manual) {
      if (commit.current) {
        clearTimeout(commit.current);
        commit.current = null;
      }
      mutate(() => setGpuClockAuto(scope, target, appid));
      return;
    }
    // Turning manual ON: pin the current window (seed from the shown range).
    const cur = stateRef.current;
    if (!cur) return;
    setState({ ...cur, manual: true, ...(scope === "global" && cur.global_manual !== undefined ? { global_manual: true } : {}) }); // optimistic
    mutate(() => setGpuClock(
      cur.min ?? cur.range_min ?? 0,
      cur.max ?? cur.range_max ?? 0,
      scope,
      target,
      appid,
    ));
  }, [appid, mutate, scope, target]);

  const setWindow = useCallback((min: number, max: number) => {
    editEpoch.current += 1;
    setState((cur) => (cur ? { ...cur, manual: true, min, max, ...(scope === "global" && cur.global_manual !== undefined ? { global_manual: true, global_min: min, global_max: max } : {}) } : cur)); // optimistic
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      commit.current = null;
      mutate(() => setGpuClock(min, max, scope, target, appid));
    }, 200);
  }, [appid, mutate, scope, target]);

  const guard = useGamePowerChangeGuard(scope, appid, state?.game_power_owner, state?.steam_readback_available);
  const missingSteamReadback = scope === "game" && state?.game_power_owner?.owner === "steam" && state.steam_readback_available === false;
  return { state: missingSteamReadback && shown ? { ...shown, supported: false } : shown, scope, game, onScope, setManual: guard(setManual), setWindow: guard(setWindow) };
}
