import { useCallback, useEffect, useState } from "react";
import {
  getControllerConfig,
  resetController,
  setControllerButton,
  setControllerFollowGlobal,
  setControllerSetting,
  type ControllerConfig,
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
}

/**
 * Owns the Mandos controller config + the global/per-game scope. Fetches on mount
 * and whenever the running game changes (the backend keys the remap by the running
 * appid); clears first so a game switch never shows the previous game's remap. The
 * scope tab reflects the game's active remap and IS the control (shared wiring).
 */
export function useController(): ControllerControl {
  const game = useRunningGame();
  const [config, setConfig] = useState<ControllerConfig | null>(null);

  const appid = game?.appid;
  useEffect(() => {
    setConfig(null);
    getControllerConfig().then(setConfig).catch(() => {});
  }, [appid]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => { setControllerFollowGlobal(f, a).then(setConfig).catch(() => {}); },
    [],
  );
  const { scope, onScope } = useScopeSync(appid, config?.follows_global, applyFollow);

  // Write target for the active scope (a game write needs the appid; global ignores it).
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

  return { config, scope, game, onScope, onSetButton, onSetSetting, onReset };
}
