import { useCallback, useEffect, useRef, useState } from "react";
import {
  getFanCurveState,
  setFanPreset,
  setFanCurvePoints,
  setFanCurveAuto,
  setFanAdaptive,
  setFanAdaptiveBias,
  setFanExperimental,
  FanCurveState,
  FanScope,
  FanPreset,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { Point } from "./curve";

export interface FanCurveControl {
  state: FanCurveState | null;
  scope: FanScope;
  game: ReturnType<typeof useRunningGame>;
  saved: boolean;
  refresh: () => void;
  setScope: (s: FanScope) => void;
  onPreset: (preset: FanPreset) => void;
  onCustomMode: () => void;
  onAdaptive: () => void;
  onAdaptiveBias: (bias: number) => void;
  onCurve: (points: Point[]) => void;
  onExperimental: (enabled: boolean) => void;
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
  const [scope, setScope] = useState<FanScope>("global");
  const [saved, setSaved] = useState(false);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    getFanCurveState().then(setState).catch(() => {});
  }, []);

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
    setScope(appid ? "game" : "global");
    refresh();
  }, [appid, refresh]);

  // Don't fire a debounced sysfs write after the tab unmounts mid-drag.
  useEffect(() => () => {
    if (commit.current) clearTimeout(commit.current);
    if (savedTimer.current) clearTimeout(savedTimer.current);
  }, []);

  // Resolve which profile a write targets: the running game's id when in game
  // scope, else null (global).
  const resolveTarget = useCallback((): { appid: string | null; scope: FanScope } => {
    const targetAppid = scope === "game" && game ? game.appid : null;
    return { appid: targetAppid, scope: targetAppid ? "game" : "global" };
  }, [scope, game]);

  const onAdaptive = useCallback(() => {
    const { appid: targetAppid, scope: targetScope } = resolveTarget();
    setFanAdaptive(targetScope, targetAppid).then(setState).catch(() => {});
  }, [resolveTarget]);

  const onPreset = useCallback(
    (preset: FanPreset) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      if (preset === "auto") {
        setFanCurveAuto(targetScope, targetAppid).then(setState).catch(() => {});
        return;
      }
      if (preset === "adaptive") {
        onAdaptive();
        return;
      }
      setFanPreset(preset, targetScope, targetAppid).then(setState).catch(() => {});
    },
    [resolveTarget, onAdaptive],
  );

  // The silence↔cool dial in adaptive mode: optimistic local bias, debounced commit
  // (mirrors onCurve). The RPC drives the biased learned curve to the hardware.
  const onAdaptiveBias = useCallback(
    (bias: number) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setState((cur) => (cur ? { ...cur, preset: "adaptive", bias } : cur)); // optimistic
      if (commit.current) clearTimeout(commit.current);
      commit.current = setTimeout(() => {
        setFanAdaptiveBias(bias, targetScope, targetAppid).then(setState).catch(() => {});
      }, 200);
    },
    [resolveTarget],
  );

  // Enter custom editing: seed from the curve currently shown (the active preset
  // or the existing custom curve) and persist it as a custom profile so the dots
  // become editable from a familiar starting shape.
  const onCustomMode = useCallback(() => {
    if (state?.preset === "custom") return; // already editing
    const seed = shownPoints(state);
    if (!seed) return;
    const { appid: targetAppid, scope: targetScope } = resolveTarget();
    setState((cur) => (cur ? { ...cur, preset: "custom", points: seed } : cur));
    setFanCurvePoints(seed, targetScope, targetAppid)
      .then((next) => {
        setState(next);
        flashSaved();
      })
      .catch(() => {});
  }, [state, resolveTarget, flashSaved]);

  const onCurve = useCallback(
    (points: Point[]) => {
      const { appid: targetAppid, scope: targetScope } = resolveTarget();
      setState((cur) => (cur ? { ...cur, preset: "custom", points } : cur)); // optimistic
      if (commit.current) clearTimeout(commit.current);
      commit.current = setTimeout(() => {
        setFanCurvePoints(points, targetScope, targetAppid)
          .then((next) => {
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
    setFanExperimental(enabled).then(setState).catch(() => {});
  }, []);

  return { state, scope, game, saved, refresh, setScope, onPreset, onCustomMode, onAdaptive, onAdaptiveBias, onCurve, onExperimental };
}
