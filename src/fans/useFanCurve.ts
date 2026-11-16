import { useCallback, useEffect, useRef, useState } from "react";
import {
  getFanCurveState,
  setFanFollowGlobal,
  setFanPreset,
  setFanCurvePoints,
  setFanCurveAuto,
  setFanSplit,
  setFanAdaptive,
  setFanAdaptiveBias,
  setFanExperimental,
  resetFanControl,
  FanCurveState,
  FanScope,
  FanPreset,
  SplitFanKey,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";
import { useMountedRef } from "../hooks/useMountedRef";
import { Point } from "./curve";

export interface FanCurveControl {
  state: FanCurveState | null;
  scope: FanScope;
  game: ReturnType<typeof useRunningGame>;
  saved: boolean;
  refresh: () => void;
  onScope: (s: FanScope) => void;
  onPreset: (preset: FanPreset) => void;
  onCustomMode: () => void;
  onAdaptive: () => void;
  onAdaptiveBias: (bias: number) => void;
  onCurve: (points: Point[]) => void;
  onSplit: (split: boolean) => void;
  onChannelCurve: (channel: SplitFanKey, points: Point[]) => void;
  onExperimental: (enabled: boolean) => void;
  onReset: () => Promise<boolean>;
}

const BALANCED = "balanced";

/** Points currently shown for a state: the stored curve, else the balanced
 *  preset as a sensible starting shape. */
export function shownPoints(s: FanCurveState | null): Point[] | null {
  if (!s) return null;
  if (s.points) return s.points as Point[];
  return (s.presets.find((p) => p.id === BALANCED)?.points as Point[]) ?? null;
}

/**
 * Owns the fan-curve state (preset/points), the global/per-game scope, and the
 * debounced commit when dragging the curve. Mirrors PotenciaSection's pattern:
 * optimistic local update on drag, RPC commit after 200 ms; preset/auto are
 * discrete (no optimism — the returned state is the source of truth).
 */
export function useFanCurve(): FanCurveControl {
  const game = useRunningGame();
  const [state, setState] = useState<FanCurveState | null>(null);
  const [saved, setSaved] = useState(false);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // One debounce per fan in per-channel mode: dragging CPU must not cancel a pending GPU commit.
  const writeGen = useRef(0);
  const channelCommit = useRef<Partial<Record<SplitFanKey, ReturnType<typeof setTimeout>>>>({});

  // Don't apply a late RPC response after the section/modal unmounts.
  const alive = useMountedRef();
  const setStateSafe = useCallback((s: FanCurveState) => { if (alive.current) setState(s); }, [alive]);

  const refresh = useCallback(() => {
    getFanCurveState().then(setStateSafe).catch(() => {});
  }, [setStateSafe]);

  // Flash a transient "Guardado" confirmation after a successful custom commit.
  const flashSaved = useCallback(() => {
    setSaved(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(false), 1500);
  }, []);

  // The appid effect owns the initial fetch too (it fires on mount), so there's
  // no separate mount-only refresh.
  const appid = game?.appid;
  useEffect(() => {
    // Cancel any in-flight drag commit captured against the previous scope — its
    // late response would otherwise overwrite the freshly-refreshed new scope.
    if (commit.current) clearTimeout(commit.current);
    Object.values(channelCommit.current).forEach((timer) => timer && clearTimeout(timer));
    channelCommit.current = {};
    refresh();
  }, [appid, refresh]);

  // The scope tab reflects the game's active fan profile and IS the control (shared
  // wiring): picking Global makes the running game follow the global curve, the game
  // tab activates its own, neither deletes the other.
  const applyFollow = useCallback(
    (f: boolean, a: string) => setFanFollowGlobal(f, a)
      .then((next) => {
        setStateSafe(next);
        return next.follows_global === f;
      })
      .catch(() => false),
    [setStateSafe],
  );
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);

  // Don't fire a debounced sysfs write after the tab unmounts mid-drag.
  useEffect(() => () => {
    if (commit.current) clearTimeout(commit.current);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    Object.values(channelCommit.current).forEach((timer) => timer && clearTimeout(timer));
  }, []);

  // Resolve which profile a write targets: the running game's id when in game
  // scope, else null (global).
  const resolveTarget = useCallback((): { appid: string | null; scope: FanScope } => {
    const targetAppid = scope === "game" && game ? game.appid : null;
    return { appid: targetAppid, scope: targetAppid ? "game" : "global" };
  }, [scope, game]);

  const onAdaptive = useCallback(() => {
    const { appid: targetAppid, scope: targetScope } = resolveTarget();
    setFanAdaptive(targetScope, targetAppid).then(setStateSafe).catch(() => {});
  }, [resolveTarget, setStateSafe]);

  const onPreset = useCallback(
    (preset: FanPreset) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      if (preset === "auto") {
        setFanCurveAuto(targetScope, targetAppid).then(setStateSafe).catch(() => {});
        return;
      }
      if (preset === "adaptive") {
        onAdaptive();
        return;
      }
      setFanPreset(preset, targetScope, targetAppid).then(setStateSafe).catch(() => {});
    },
    [resolveTarget, onAdaptive, setStateSafe],
  );

  // The silence↔cool dial in adaptive mode: optimistic local bias, debounced commit
  // (mirrors onCurve). The RPC drives the biased learned curve to the hardware.
  const onAdaptiveBias = useCallback(
    (bias: number) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setState((cur) => (cur ? { ...cur, preset: "adaptive", bias } : cur)); // optimistic
      if (commit.current) clearTimeout(commit.current);
      commit.current = setTimeout(() => {
        setFanAdaptiveBias(bias, targetScope, targetAppid).then(setStateSafe).catch(() => {});
      }, 200);
    },
    [resolveTarget, setStateSafe],
  );

  const onCustomMode = useCallback(() => {
    if (state?.preset === "custom") return; // already editing
    if (state?.split) {
      // Per-channel: each fan resumes ITS last manual curve (else the one it shows).
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      const seeds = (["cpu", "gpu"] as SplitFanKey[]).map((key) => ({
        key,
        points: (state.custom_points_by_channel?.[key]
          ?? state.channels?.find((c) => c.key === key)?.points
          ?? shownPoints(state)) as Point[] | null,
      }));
      if (seeds.some((seed) => !seed.points)) return;
      setState((cur) => (cur ? { ...cur, preset: "custom" } : cur));
      seeds
        .reduce(
          (chain, seed) => chain.then(() => setFanCurvePoints(seed.points as Point[], targetScope, targetAppid, seed.key)),
          Promise.resolve(null as FanCurveState | null),
        )
        .then((next) => { if (next && alive.current) setStateSafe(next); })
        .catch(() => {});
      return;
    }
    const seed = state?.custom_points ?? shownPoints(state);
    if (!seed) return;
    const { appid: targetAppid, scope: targetScope } = resolveTarget();
    setState((cur) => (cur ? { ...cur, preset: "custom", points: seed } : cur));
    setFanCurvePoints(seed, targetScope, targetAppid)
      .then((next) => {
        if (!alive.current) return;
        setState(next);
        flashSaved();
      })
      .catch(() => {});
  }, [state, resolveTarget, flashSaved, alive, setStateSafe]);

  const onCurve = useCallback(
    (points: Point[]) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setState((cur) => (cur ? { ...cur, preset: "custom", points } : cur)); // optimistic
      if (commit.current) clearTimeout(commit.current);
      commit.current = setTimeout(() => {
        const gen = ++writeGen.current;
        setFanCurvePoints(points, targetScope, targetAppid)
          .then((next) => {
            if (!alive.current || gen !== writeGen.current) return;
            setState(next);
            flashSaved();
          })
          .catch(() => {});
      }, 200);
    },
    [resolveTarget, flashSaved],
  );

  // Joined <-> per-channel. The returned state is the source of truth (the backend seeds
  // both channels from the current curve), so no optimism.
  const onSplit = useCallback(
    (split: boolean) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setFanSplit(split, targetScope, targetAppid).then(setStateSafe).catch(() => {});
    },
    [resolveTarget, setStateSafe],
  );

  const onChannelCurve = useCallback(
    (channel: SplitFanKey, points: Point[]) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setState((cur) => (cur ? {
        ...cur,
        preset: "custom",
        channels: cur.channels?.map((c) => (c.key === channel ? { ...c, preset: "custom", points } : c)),
      } as FanCurveState : cur)); // optimistic
      const pending = channelCommit.current[channel];
      if (pending) clearTimeout(pending);
      channelCommit.current[channel] = setTimeout(() => {
        delete channelCommit.current[channel];
        const gen = ++writeGen.current;
        setFanCurvePoints(points, targetScope, targetAppid, channel)
          .then((next) => {
            if (!alive.current || gen !== writeGen.current) return;
            setState(next);
            flashSaved();
          })
          .catch(() => {});
      }, 200);
    },
    [resolveTarget, flashSaved],
  );

  // Opt in/out of experimental EC fan control (Legion Go S). The returned state is
  // the source of truth (backend swaps the fan backend), so no optimism.
  const onExperimental = useCallback((enabled: boolean) => {
    setFanExperimental(enabled).then(setStateSafe).catch(() => {});
  }, [setStateSafe]);

  const onReset = useCallback(
    () =>
      resetFanControl()
        .then((next) => {
          setStateSafe(next);
          return next.reset_ok ?? false;
        })
        .catch(() => false),
    [setStateSafe],
  );

  return { state, scope, game, saved, refresh, onScope, onPreset, onCustomMode, onAdaptive, onAdaptiveBias, onCurve, onSplit, onChannelCurve, onExperimental, onReset };
}
