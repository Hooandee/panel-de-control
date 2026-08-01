import { useCallback, useEffect, useRef, useState } from "react";
import {
  getControllerConfig,
  getControllerDiagnostics,
  resetController,
  setControllerButton,
  setControllerFollowGlobal,
  setControllerSetting,
  setControllerVibration,
  testControllerVibration,
  type ControllerConfig,
  type Scope,
} from "../api";
import {
  normalizeControllerDiagnostics,
  type ControllerDiagnostics,
} from "./diagnostics";
import { valueToTarget } from "./logic";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";

export interface ControllerControl {
  config: ControllerConfig | null;
  scope: Scope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (s: Scope) => void;
  /** Empty value → revert this one button to the device default. */
  onSetButton: (source: string, value: string) => void;
  onSetSetting: (field: string, value: string) => void;
  onSetVibration: (patch: {
    enabled?: boolean;
    value?: number;
    left?: number;
    right?: number;
  }) => void;
  onTestVibration: (strength: number) => void;
  onReset: () => void;
}

export function useController(): ControllerControl {
  const game = useRunningGame();
  const [config, setConfig] = useState<ControllerConfig | null>(null);
  const requestSequence = useRef(0);
  const mounted = useRef(true);
  const appidRef = useRef<string | undefined>(game?.appid);
  const vibrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingVibration = useRef<{
    patch: { enabled?: boolean; value?: number; left?: number; right?: number };
    scope: Scope;
    appid: string | null;
    viewAppid: string | undefined;
  } | null>(null);

  const appid = game?.appid;
  appidRef.current = appid;

  const accept = useCallback((
    promise: Promise<ControllerConfig>,
    viewAppid: string | undefined,
  ) => {
    const sequence = ++requestSequence.current;
    promise.then((value) => {
      if (
        mounted.current
        && sequence === requestSequence.current
        && appidRef.current === viewAppid
      ) setConfig(value);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    setConfig(null);
    getControllerConfig().then((value) => {
      if (
        mounted.current
        && sequence === requestSequence.current
        && appidRef.current === appid
      ) setConfig(value);
    }).catch(() => {});
  }, [appid]);

  const sendPendingVibration = useCallback(() => {
    if (vibrationTimer.current !== null) {
      clearTimeout(vibrationTimer.current);
      vibrationTimer.current = null;
    }
    const pending = pendingVibration.current;
    pendingVibration.current = null;
    if (!pending) return;
    accept(
      setControllerVibration(pending.patch, pending.scope, pending.appid),
      pending.viewAppid,
    );
  }, [accept]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestSequence.current += 1;
      if (vibrationTimer.current !== null) clearTimeout(vibrationTimer.current);
      const pending = pendingVibration.current;
      pendingVibration.current = null;
      if (pending) {
        setControllerVibration(pending.patch, pending.scope, pending.appid)
          .catch(() => {});
      }
    };
  }, []);

  const applyFollow = useCallback(
    (f: boolean, a: string) => {
      accept(setControllerFollowGlobal(f, a), appidRef.current);
    },
    [accept],
  );
  const { scope, onScope } = useScopeSync(appid, config?.follows_global, applyFollow);

  const targetAppid = scope === "game" && game ? game.appid : null;
  const targetScope: Scope = targetAppid ? "game" : "global";

  const onSetButton = useCallback(
    (source: string, value: string) => {
      accept(
        setControllerButton(
          source,
          value ? [valueToTarget(value)] : [],
          targetScope,
          targetAppid,
        ),
        appid,
      );
    },
    [targetScope, targetAppid, appid, accept],
  );
  const onSetSetting = useCallback(
    (field: string, value: string) => {
      accept(setControllerSetting(field, value), appidRef.current);
    },
    [accept],
  );
  const onSetVibration = useCallback(
    (patch: { enabled?: boolean; value?: number; left?: number; right?: number }) => {
      const next = {
        patch,
        scope: targetScope,
        appid: targetAppid,
        viewAppid: appidRef.current,
      };
      let current = pendingVibration.current;
      if (
        current
        && (
          current.scope !== next.scope
          || current.appid !== next.appid
        )
      ) {
        sendPendingVibration();
        current = null;
      }
      if (
        current
        && current.scope === next.scope
        && current.appid === next.appid
      ) next.patch = { ...current.patch, ...patch };
      pendingVibration.current = next;
      if (typeof patch.enabled === "boolean") {
        sendPendingVibration();
        return;
      }
      if (vibrationTimer.current !== null) clearTimeout(vibrationTimer.current);
      vibrationTimer.current = setTimeout(sendPendingVibration, 150);
    },
    [targetScope, targetAppid, sendPendingVibration],
  );
  const onTestVibration = useCallback(
    (strength: number) => { testControllerVibration(strength).catch(() => {}); },
    [],
  );
  const onReset = useCallback(
    () => {
      accept(resetController(targetScope, targetAppid), appidRef.current);
    },
    [targetScope, targetAppid, accept],
  );

  return {
    config, scope, game, onScope, onSetButton, onSetSetting,
    onSetVibration, onTestVibration, onReset,
  };
}

export function useControllerDiagnostics(): ControllerDiagnostics | null {
  const [diagnostics, setDiagnostics] = useState<ControllerDiagnostics | null>(null);

  useEffect(() => {
    let mounted = true;
    getControllerDiagnostics()
      .then((value) => {
        if (mounted) setDiagnostics(normalizeControllerDiagnostics(value));
      })
      .catch(() => {
        if (mounted) setDiagnostics(normalizeControllerDiagnostics(null));
      });
    return () => { mounted = false; };
  }, []);

  return diagnostics;
}
