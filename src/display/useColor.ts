import { useCallback, useEffect, useRef, useState } from "react";
import {
  getColorState,
  setSaturation,
  setColorFollowGlobal,
  previewCalibration,
  setCalibration,
  applyOledLook,
  applyColorPreset,
  resetColor,
  ColorState,
  ColorPreset,
  Scope,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { pickCalibration } from "./color";

export interface ColorControl {
  state: ColorState | null;
  scope: Scope;
  game: ReturnType<typeof useRunningGame>;
  /** Seconds left before an unconfirmed calibration auto-reverts (null = none pending). */
  revertIn: number | null;
  onScope: (s: Scope) => void;
  onSaturation: (value: number) => void;
  onCalibration: (patch: Partial<ColorPreset>) => void;
  confirmCalibration: () => void;
  onOledLook: () => void;
  onPreset: (key: string) => void;
  onReset: () => void;
}

/**
 * Owns the Pantalla color state + the global/per-game scope for SATURATION.
 * Saturation saves directly (can't make the screen illegible). Calibration
 * (temperature/contrast) is PREVIEWED live and auto-reverts after the backend
 * window unless confirmed — a UI countdown mirrors it and refreshes on expiry.
 */
export function useColor(): ColorControl {
  const game = useRunningGame();
  const [state, setState] = useState<ColorState | null>(null);
  const [scope, setScope] = useState<Scope>("global");
  const [revertIn, setRevertIn] = useState<number | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdown = useRef<ReturnType<typeof setInterval> | null>(null);
  const remaining = useRef(0);
  const stateRef = useRef<ColorState | null>(null);
  stateRef.current = state;

  const refresh = useCallback(() => {
    getColorState().then(setState).catch(() => {});
  }, []);

  const stopCountdown = useCallback(() => {
    if (countdown.current) clearInterval(countdown.current);
    countdown.current = null;
    setRevertIn(null);
  }, []);

  // Fetch on mount + whenever the running game changes (also snaps scope). A game
  // change invalidates any in-flight calibration preview (the backend drops it in
  // _reapply_all), so cancel the pending commit AND the mirror countdown to stay in
  // sync — otherwise the confirm bar keeps ticking against a preview that's gone.
  const appid = game?.appid;
  useEffect(() => {
    if (commit.current) clearTimeout(commit.current);
    stopCountdown();
    refresh();
  }, [appid, refresh, stopCountdown]);

  // Keep the tab in sync with the game's ACTIVE saturation profile (own vs global).
  useEffect(() => {
    if (!state) return;
    setScope(appid && !state.follows_global ? "game" : "global");
  }, [appid, state?.follows_global]);

  // The tab IS the control: Global makes the running game follow the global saturation;
  // the game tab activates its own. Neither deletes the other.
  const onScope = useCallback(
    (next: Scope) => {
      setScope(next);
      if (appid) setColorFollowGlobal(next === "global", appid).then(setState).catch(() => {});
    },
    [appid],
  );

  useEffect(() => () => {
    if (commit.current) clearTimeout(commit.current);
    if (countdown.current) clearInterval(countdown.current);
  }, []);

  const onSaturation = useCallback(
    (value: number) => {
      const targetAppid = scope === "game" && game ? game.appid : null;
      const targetScope: Scope = targetAppid ? "game" : "global";
      setState((cur) => (cur ? { ...cur, saturation: value } : cur)); // optimistic
      if (commit.current) clearTimeout(commit.current);
      commit.current = setTimeout(() => {
        setSaturation(value, targetScope, targetAppid).then(setState).catch(() => {});
      }, 200);
    },
    [scope, game],
  );

  // (re)start the mirror countdown; on expiry the backend has already reverted, so
  // just refresh to show the restored values.
  const startCountdown = useCallback((secs: number) => {
    remaining.current = secs;
    setRevertIn(secs);
    if (countdown.current) clearInterval(countdown.current);
    countdown.current = setInterval(() => {
      remaining.current -= 1;
      if (remaining.current <= 0) {
        stopCountdown();
        refresh();
      } else {
        setRevertIn(remaining.current);
      }
    }, 1000);
  }, [refresh, stopCountdown]);

  const onCalibration = useCallback((patch: Partial<ColorPreset>) => {
    const base = stateRef.current;
    if (!base) return;
    const next = { ...base, ...patch, preview: true };
    setState(next); // optimistic
    startCountdown(base.revert_seconds || 15);
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      previewCalibration(pickCalibration(next)).then(setState).catch(() => {});
    }, 200);
  }, [startCountdown]);

  // Write target for the active scope (game writes need the appid; global ignores it).
  const wScope: Scope = scope === "game" && game ? "game" : "global";
  const wTarget = wScope === "game" && game ? game.appid : null;

  const confirmCalibration = useCallback(() => {
    const cur = stateRef.current;
    if (!cur) return;
    stopCountdown();
    if (commit.current) clearTimeout(commit.current);
    setCalibration(pickCalibration(cur), wScope, wTarget).then(setState).catch(() => {});
  }, [stopCountdown, wScope, wTarget]);

  const onOledLook = useCallback(() => {
    stopCountdown();
    applyOledLook(wScope, wTarget).then(setState).catch(() => {});
  }, [stopCountdown, wScope, wTarget]);

  const onPreset = useCallback((key: string) => {
    stopCountdown();
    applyColorPreset(key, wScope, wTarget).then(setState).catch(() => {});
  }, [stopCountdown, wScope, wTarget]);

  const onReset = useCallback(() => {
    stopCountdown();
    resetColor().then(setState).catch(() => {});
  }, [stopCountdown]);

  return {
    state, scope, game, revertIn, onScope,
    onSaturation, onCalibration, confirmCalibration, onOledLook, onPreset, onReset,
  };
}
