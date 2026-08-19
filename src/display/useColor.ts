import { useCallback, useEffect, useRef, useState } from "react";
import {
  getColorState,
  setColorFollowGlobal,
  previewCalibration,
  setCalibration,
  discardCalibration as discardCalibrationRpc,
  previewOledLook,
  previewColorPreset,
  resetColor,
  ColorState,
  ColorPreset,
  Scope,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";
import { pickColor } from "./color";

export interface ColorControl {
  state: ColorState | null;
  scope: Scope;
  game: ReturnType<typeof useRunningGame>;
  revertIn: number | null;
  saving: boolean;
  onScope: (s: Scope) => void;
  onSaturation: (value: number) => void;
  onCalibration: (patch: Partial<ColorPreset>) => void;
  confirmCalibration: () => Promise<void>;
  discardCalibration: () => Promise<void>;
  onOledLook: () => void;
  onPreset: (key: string) => void;
  onReset: () => void;
}

interface PreviewTarget {
  scope: Scope;
  appid: string | null;
  contextAppid: string | null;
}

function clearTimer(timer: { current: ReturnType<typeof setTimeout> | null }): void {
  if (timer.current !== null) clearTimeout(timer.current);
  timer.current = null;
}

export function useColor(): ColorControl {
  const game = useRunningGame();
  const [state, setState] = useState<ColorState | null>(null);
  const [revertIn, setRevertIn] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const previewCommit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdown = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconcile = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remaining = useRef(0);
  const probeAttempts = useRef(0);
  const savingRef = useRef(false);
  const previewTarget = useRef<PreviewTarget | null>(null);
  const previewEpoch = useRef(0);
  const previewRequest = useRef<Promise<ColorState | null> | null>(null);
  const previewPatch = useRef<Partial<ColorPreset>>({});
  const contextRef = useRef<string | null>(null);
  const stateRef = useRef<ColorState | null>(null);
  stateRef.current = state;
  contextRef.current = game?.appid ?? null;

  const refresh = useCallback(() => {
    getColorState().then(setState).catch(() => {});
  }, []);

  const stopCountdown = useCallback(() => {
    if (countdown.current) clearInterval(countdown.current);
    countdown.current = null;
    setRevertIn(null);
  }, []);

  const appid = game?.appid;
  useEffect(() => {
    clearTimer(previewCommit);
    previewPatch.current = {};
    if (reconcile.current) clearTimeout(reconcile.current);
    previewEpoch.current += 1;
    stopCountdown();
    previewTarget.current = null;
    savingRef.current = false;
    setSaving(false);
    refresh();
  }, [appid, refresh, stopCountdown]);

  useEffect(() => {
    if (state?.supported === true) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const probe = async () => {
      if (!active || probeAttempts.current >= 60) return;
      probeAttempts.current += 1;
      try {
        const next = await getColorState();
        if (!active) return;
        setState(next);
        if (!next.supported) timer = setTimeout(probe, 2000);
      } catch {
        if (active) timer = setTimeout(probe, 2000);
      }
    };
    timer = setTimeout(probe, 2000);
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [state?.supported]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => {
      if (savingRef.current) return Promise.resolve(false);
      savingRef.current = true;
      setSaving(true);
      return setColorFollowGlobal(f, a, game?.appid ?? null)
        .then((next) => {
          stateRef.current = next;
          setState(next);
          return next.follows_global === f;
        })
        .catch(() => false)
        .finally(() => {
          savingRef.current = false;
          setSaving(false);
        });
    },
    [game?.appid],
  );
  const { scope, onScope: syncScope } = useScopeSync(appid, state?.follows_global, applyFollow);

  const wScope: Scope = scope === "game" && game ? "game" : "global";
  const wTarget = wScope === "game" && game ? game.appid : null;
  const wContext = game?.appid ?? null;

  useEffect(() => () => {
    if (previewCommit.current) clearTimeout(previewCommit.current);
    if (countdown.current) clearInterval(countdown.current);
    if (reconcile.current) clearTimeout(reconcile.current);
  }, []);

  const acceptState = useCallback((next: ColorState): boolean => {
    stateRef.current = next;
    setState(next);
    if (next.preview) return false;
    previewEpoch.current += 1;
    previewTarget.current = null;
    stopCountdown();
    return true;
  }, [stopCountdown]);

  const discardPreview = useCallback(async (): Promise<boolean> => {
    if (savingRef.current) return false;
    clearTimer(previewCommit);
    previewPatch.current = {};
    const epoch = previewEpoch.current;
    const pending = previewRequest.current;
    savingRef.current = true;
    setSaving(true);
    try {
      if (pending) await pending;
      if (epoch !== previewEpoch.current) return false;
      const context = previewTarget.current?.contextAppid ?? contextRef.current;
      const next = await discardCalibrationRpc(context);
      return epoch === previewEpoch.current && acceptState(next);
    } catch {
      try {
        const next = await getColorState();
        return epoch === previewEpoch.current && acceptState(next);
      } catch {
        return false;
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [acceptState]);

  const expirePreview = useCallback(() => {
    if (reconcile.current) clearTimeout(reconcile.current);
    const epoch = previewEpoch.current;
    let attempts = 0;
    const tryDiscard = async () => {
      if (epoch !== previewEpoch.current) return;
      if (await discardPreview()) return;
      if (epoch !== previewEpoch.current) return;
      attempts += 1;
      if (attempts < 5) reconcile.current = setTimeout(tryDiscard, 1000);
    };
    void tryDiscard();
  }, [discardPreview]);

  const startCountdown = useCallback((secs: number) => {
    remaining.current = Math.max(0, Math.ceil(secs));
    setRevertIn(remaining.current);
    if (reconcile.current) clearTimeout(reconcile.current);
    if (countdown.current) clearInterval(countdown.current);
    if (remaining.current === 0) {
      expirePreview();
      return;
    }
    countdown.current = setInterval(() => {
      remaining.current -= 1;
      if (remaining.current <= 0) {
        if (countdown.current) clearInterval(countdown.current);
        countdown.current = null;
        setRevertIn(0);
        expirePreview();
      } else {
        setRevertIn(remaining.current);
      }
    }, 1000);
  }, [expirePreview]);

  const reconcilePreview = useCallback(async (epoch: number) => {
    try {
      const next = await getColorState();
      if (epoch !== previewEpoch.current) return;
      acceptState(next);
      if (next.preview) {
        startCountdown(next.revert_remaining ?? next.revert_seconds ?? 15);
      }
    } catch {
      // The existing countdown remains the safe fallback when readback also fails.
    }
  }, [acceptState, startCountdown]);

  useEffect(() => {
    if (!state?.preview) {
      if (revertIn !== null) stopCountdown();
      previewTarget.current = null;
      return;
    }
    if (!previewTarget.current) {
      const targetScope = state.preview_scope
        ?? (state.appid !== null && !state.follows_global ? "game" : "global");
      previewTarget.current = {
        scope: targetScope,
        appid: targetScope === "game" ? (state.preview_appid ?? state.appid ?? wTarget) : null,
        contextAppid: state.appid ?? wContext,
      };
    }
    if (revertIn === null) {
      startCountdown(state.revert_remaining ?? state.revert_seconds ?? 15);
    }
  }, [
    state?.preview, state?.revert_remaining, state?.revert_seconds,
    state?.preview_scope, state?.preview_appid, state?.appid,
    revertIn, startCountdown, stopCountdown, wScope, wTarget, wContext,
  ]);

  const onCalibration = useCallback((patch: Partial<ColorPreset>) => {
    if (savingRef.current) return;
    const base = stateRef.current;
    if (!base) return;
    previewPatch.current = { ...previewPatch.current, ...patch };
    const target = previewTarget.current ?? {
      scope: wScope,
      appid: wTarget,
      contextAppid: wContext,
    };
    previewTarget.current = target;
    const next = { ...base, ...patch, preview: true };
    const epoch = ++previewEpoch.current;
    stateRef.current = next;
    setState(next);
    startCountdown(base.revert_seconds || 15);
    clearTimer(previewCommit);
    previewCommit.current = setTimeout(() => {
      previewCommit.current = null;
      const queuedPatch = previewPatch.current;
      previewPatch.current = {};
      const pending = previewRequest.current;
      const request = (async () => {
        const previous = pending ? await pending : null;
        if (epoch !== previewEpoch.current) return previous;
        const latest = { ...(previous ?? stateRef.current ?? base), ...queuedPatch, preview: true };
        stateRef.current = latest;
        setState(latest);
        try {
          const response = await previewCalibration(
            pickColor(latest), target.scope, target.appid, target.contextAppid,
          );
          if (epoch === previewEpoch.current) {
            acceptState(response);
            if (response.preview) {
              startCountdown(response.revert_remaining ?? response.revert_seconds ?? 15);
            }
          }
          return response;
        } catch {
          await reconcilePreview(epoch);
          return null;
        }
      })();
      previewRequest.current = request;
      void request.finally(() => {
        if (previewRequest.current === request) previewRequest.current = null;
      });
    }, 200);
  }, [acceptState, reconcilePreview, startCountdown, wScope, wTarget, wContext]);

  const onSaturation = useCallback((value: number) => {
    onCalibration({ saturation: value });
  }, [onCalibration]);

  const confirmCalibration = useCallback(async () => {
    if (!stateRef.current || savingRef.current) return;
    const target = previewTarget.current ?? {
      scope: wScope,
      appid: wTarget,
      contextAppid: wContext,
    };
    clearTimer(previewCommit);
    previewPatch.current = {};
    const epoch = previewEpoch.current;
    const pending = previewRequest.current;
    savingRef.current = true;
    setSaving(true);
    try {
      if (pending) await pending;
      if (epoch !== previewEpoch.current) return;
      const color = stateRef.current;
      if (!color) return;
      const next = await setCalibration(
        pickColor(color), target.scope, target.appid, target.contextAppid,
      );
      if (epoch === previewEpoch.current) acceptState(next);
    } catch {
      await reconcilePreview(epoch);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [acceptState, reconcilePreview, wScope, wTarget, wContext]);

  const discardCalibration = useCallback(async () => {
    await discardPreview();
  }, [discardPreview]);

  const onScope = useCallback((next: Scope) => {
    if (savingRef.current) return;
    if (!previewTarget.current && !stateRef.current?.preview) {
      syncScope(next);
      return;
    }
    void discardPreview().then((discarded) => {
      if (discarded) syncScope(next);
    });
  }, [discardPreview, syncScope]);

  const runPreviewAction = useCallback((action: () => Promise<ColorState>) => {
    if (savingRef.current) return;
    clearTimer(previewCommit);
    previewPatch.current = {};
    previewTarget.current = {
      scope: wScope,
      appid: wTarget,
      contextAppid: wContext,
    };
    if (stateRef.current?.preview) {
      startCountdown(stateRef.current.revert_seconds || 15);
    }
    const epoch = ++previewEpoch.current;
    const pending = previewRequest.current;
    const request = (async () => {
      const previous = pending ? await pending : null;
      if (epoch !== previewEpoch.current) return previous;
      try {
        const next = await action();
        if (epoch === previewEpoch.current) {
          acceptState(next);
          if (next.preview) {
            startCountdown(next.revert_remaining ?? next.revert_seconds ?? 15);
          }
        }
        return next;
      } catch {
        await reconcilePreview(epoch);
        return null;
      }
    })();
    previewRequest.current = request;
    void request.finally(() => {
      if (previewRequest.current === request) previewRequest.current = null;
    });
  }, [acceptState, reconcilePreview, startCountdown, wScope, wTarget, wContext]);

  const onOledLook = useCallback(() => {
    runPreviewAction(() => previewOledLook(wScope, wTarget, wContext));
  }, [runPreviewAction, wScope, wTarget, wContext]);

  const onPreset = useCallback((key: string) => {
    runPreviewAction(() => previewColorPreset(key, wScope, wTarget, wContext));
  }, [runPreviewAction, wScope, wTarget, wContext]);

  const onReset = useCallback(() => {
    runPreviewAction(() => resetColor(wScope, wTarget, wContext));
  }, [runPreviewAction, wScope, wTarget, wContext]);

  return {
    state, scope, game, revertIn, saving, onScope,
    onSaturation, onCalibration, confirmCalibration, discardCalibration,
    onOledLook, onPreset, onReset,
  };
}
