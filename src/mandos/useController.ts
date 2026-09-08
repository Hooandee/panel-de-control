import { useCallback, useEffect, useRef, useState } from "react";
import {
  getControllerConfig,
  resetController,
  runControllerAction,
  setControllerButton,
  setControllerFollowGlobal,
  setControllerSetting,
  type ControllerConfig,
  type ControllerAction,
  type ControllerActionResult,
  type Scope,
} from "../api";
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
  onReset: () => void;
  actionPending: ControllerAction | null;
  actionResult: ControllerActionResult | null;
  onAction: (action: ControllerAction) => void;
}

export function useController(): ControllerControl {
  const game = useRunningGame();
  const [config, setConfig] = useState<ControllerConfig | null>(null);
  const [actionPending, setActionPending] = useState<ControllerAction | null>(null);
  const [actionResult, setActionResult] = useState<ControllerActionResult | null>(null);
  const actionInFlight = useRef(false);

  const appid = game?.appid;
  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;
    setConfig(null);
    const load = (retry: number) => {
      getControllerConfig().then((next) => {
        if (cancelled) return;
        setConfig(next);
        const awaitingKnownButtons = next.manager === "inputplumber"
          && next.kind === "remap"
          && next.device_key === "zotac_gaming_zone"
          && next.device_known === true
          && (next.buttons?.length ?? 0) === 0;
        if (awaitingKnownButtons && retry < 6) {
          retryTimer = window.setTimeout(() => load(retry + 1), 2_000);
        }
      }).catch(() => {});
    };
    load(0);
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [appid]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => setControllerFollowGlobal(f, a)
      .then((next) => {
        setConfig(next);
        return next.follows_global === f;
      })
      .catch(() => false),
    [],
  );
  const { scope, onScope } = useScopeSync(appid, config?.follows_global, applyFollow);

  const targetAppid = scope === "game" && game ? game.appid : null;
  const targetScope: Scope = targetAppid ? "game" : "global";

  const onSetButton = useCallback(
    (source: string, value: string) => {
      setControllerButton(source, value ? [valueToTarget(value)] : [], targetScope, targetAppid)
        .then(setConfig).catch(() => {});
    },
    [targetScope, targetAppid],
  );
  const onSetSetting = useCallback(
    (field: string, value: string) => { setControllerSetting(field, value).then(setConfig).catch(() => {}); },
    [],
  );
  const onReset = useCallback(
    () => { resetController(targetScope, targetAppid).then(setConfig).catch(() => {}); },
    [targetScope, targetAppid],
  );

  const onAction = useCallback((action: ControllerAction) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setActionPending(action);
    setActionResult(null);
    runControllerAction(action)
      .then((next) => {
        setConfig(next.config);
        setActionResult(next);
      })
      .catch(() => {
        setActionResult(config ? {
          action,
          outcome: "failed",
          accepted: false,
          reason: "rpc_failed",
          config,
        } : null);
      })
      .finally(() => {
        actionInFlight.current = false;
        setActionPending(null);
      });
  }, [config]);

  return {
    config,
    scope,
    game,
    onScope,
    onSetButton,
    onSetSetting,
    onReset,
    actionPending,
    actionResult,
    onAction,
  };
}
