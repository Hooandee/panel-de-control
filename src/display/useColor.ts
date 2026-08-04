import { useCallback, useEffect, useRef, useState } from "react";
import {
  getColorState,
  setSaturation,
  setHdrSaturation,
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
import { useScopeSync } from "../useScopeSync";
import { pickCalibration } from "./color";

export interface ColorControl {
  state: ColorState | null;
  scope: Scope;
  game: ReturnType<typeof useRunningGame>;
  /** Seconds left before an unconfirmed calibration auto-reverts (null = none pending). */
  revertIn: number | null;
  onScope: (s: Scope) => void;
  onSaturation: (value: number) => void;
  onHdrSaturation: (value: number) => void;
  onCalibration: (patch: Partial<ColorPreset>) => void;
  confirmCalibration: () => void;
  onOledLook: () => void;
  onPreset: (key: string) => void;
  onReset: () => void;
}

type SaturationChannel = "sdr" | "hdr";

interface PendingSaturation {
  value: number;
  scope: Scope;
  appid: string | null;
  viewAppid: string | undefined;
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
  const [revertIn, setRevertIn] = useState<number | null>(null);
  const saturationCommits = useRef<Record<
    SaturationChannel,
    ReturnType<typeof setTimeout> | null
  >>({ sdr: null, hdr: null });
  const pendingSaturations = useRef<Record<
    SaturationChannel,
    PendingSaturation | null
  >>({ sdr: null, hdr: null });
  const saturationWrites = useRef<Promise<void>>(Promise.resolve());
  const calibrationCommit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdown = useRef<ReturnType<typeof setInterval> | null>(null);
  const remaining = useRef(0);
  const stateRef = useRef<ColorState | null>(null);
  const mounted = useRef(true);
  const appidRef = useRef<string | undefined>(game?.appid);
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
  appidRef.current = appid;
  const flushSaturation = useCallback((channel: SaturationChannel) => {
    const timer = saturationCommits.current[channel];
    if (timer !== null) {
      clearTimeout(timer);
      saturationCommits.current[channel] = null;
    }
    const pending = pendingSaturations.current[channel];
    pendingSaturations.current[channel] = null;
    if (!pending) return saturationWrites.current;
    const save = channel === "hdr" ? setHdrSaturation : setSaturation;
    const commit = async () => {
      try {
        const next = await save(
          pending.value, pending.scope, pending.appid,
        );
        if (mounted.current && appidRef.current === pending.viewAppid) {
          setState(next);
        }
      } catch {}
    };
    saturationWrites.current = saturationWrites.current.then(commit, commit);
    return saturationWrites.current;
  }, []);

  const flushSaturations = useCallback(() => {
    return Promise.all([
      flushSaturation("sdr"),
      flushSaturation("hdr"),
    ]).then(() => undefined);
  }, [flushSaturation]);

  useEffect(() => {
    void flushSaturations().then(refresh);
    if (calibrationCommit.current) clearTimeout(calibrationCommit.current);
    stopCountdown();
  }, [appid, flushSaturations, refresh, stopCountdown]);

  // The scope tab reflects the game's active profile and IS the control (shared wiring).
  const applyFollow = useCallback(
    async (f: boolean, a: string) => {
      await flushSaturations();
      return setColorFollowGlobal(f, a).then((next) => {
        setState(next);
        return next.follows_global === f;
      }).catch(() => false);
    },
    [flushSaturations],
  );
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      void flushSaturations();
      if (calibrationCommit.current) clearTimeout(calibrationCommit.current);
      if (countdown.current) clearInterval(countdown.current);
    };
  }, [flushSaturations]);

  const queueSaturation = useCallback((
    channel: SaturationChannel,
    value: number,
    targetScope: Scope,
    targetAppid: string | null,
  ) => {
    const timer = saturationCommits.current[channel];
    if (timer !== null) clearTimeout(timer);
    pendingSaturations.current[channel] = {
      value,
      scope: targetScope,
      appid: targetAppid,
      viewAppid: appidRef.current,
    };
    saturationCommits.current[channel] = setTimeout(
      () => flushSaturation(channel),
      200,
    );
  }, [flushSaturation]);

  const onSaturation = useCallback(
    (value: number) => {
      const targetAppid = scope === "game" && game ? game.appid : null;
      const targetScope: Scope = targetAppid ? "game" : "global";
      setState((cur) => (cur ? { ...cur, saturation: value } : cur)); // optimistic
      queueSaturation("sdr", value, targetScope, targetAppid);
    },
    [scope, game, queueSaturation],
  );

  const onHdrSaturation = useCallback(
    (value: number) => {
      const targetAppid = scope === "game" && game ? game.appid : null;
      const targetScope: Scope = targetAppid ? "game" : "global";
      setState((current) => (
        current ? { ...current, hdr_saturation: value } : current
      ));
      queueSaturation("hdr", value, targetScope, targetAppid);
    },
    [scope, game, queueSaturation],
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
    if (calibrationCommit.current) clearTimeout(calibrationCommit.current);
    calibrationCommit.current = setTimeout(() => {
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
    if (calibrationCommit.current) clearTimeout(calibrationCommit.current);
    void flushSaturations().then(
      () => setCalibration(pickCalibration(cur), wScope, wTarget),
    ).then(setState).catch(() => {});
  }, [flushSaturations, stopCountdown, wScope, wTarget]);

  const onOledLook = useCallback(() => {
    stopCountdown();
    void flushSaturations().then(
      () => applyOledLook(wScope, wTarget),
    ).then(setState).catch(() => {});
  }, [flushSaturations, stopCountdown, wScope, wTarget]);

  const onPreset = useCallback((key: string) => {
    stopCountdown();
    void flushSaturations().then(
      () => applyColorPreset(key, wScope, wTarget),
    ).then(setState).catch(() => {});
  }, [flushSaturations, stopCountdown, wScope, wTarget]);

  const onReset = useCallback(() => {
    stopCountdown();
    void flushSaturations().then(resetColor).then(setState).catch(() => {});
  }, [flushSaturations, stopCountdown]);

  return {
    state, scope, game, revertIn, onScope,
    onSaturation, onHdrSaturation, onCalibration, confirmCalibration,
    onOledLook, onPreset, onReset,
  };
}
