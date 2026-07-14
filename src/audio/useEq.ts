import { useCallback, useEffect, useRef, useState } from "react";
import {
  AudioState,
  applyAudioPreset,
  getAudioState,
  resetAudio,
  setAudioBands,
  setAudioEnabled,
  setAudioFollowGlobal,
  Scope,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";
import { computePreamp } from "./logic";

export interface EqControl {
  state: AudioState | null;
  scope: Scope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (s: Scope) => void;
  onEnable: (enabled: boolean) => void;
  onPreset: (id: string) => void;
  onBands: (gains: number[]) => void;
  onReset: () => void;
}

/**
 * Owns the Sonido EQ state + the global/per-game scope. Band drags update the curve
 * optimistically and commit shortly after the last change (the backend applies a preset
 * by rewriting the PipeWire conf + restarting the filter-chain service, so we don't write
 * on every delta). Cancels the pending commit on unmount and on game change.
 */
export function useEq(): EqControl {
  const game = useRunningGame();
  const [state, setState] = useState<AudioState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    getAudioState().then(setState).catch(() => {});
  }, []);

  const appid = game?.appid;
  useEffect(() => {
    if (commit.current) clearTimeout(commit.current);
    refresh();
  }, [appid, refresh]);

  useEffect(() => () => {
    if (commit.current) clearTimeout(commit.current);
  }, []);

  const applyFollow = useCallback(
    (f: boolean, a: string) => { setAudioFollowGlobal(f, a).then(setState).catch(() => {}); },
    [],
  );
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);

  // Write target for the active scope (a game write needs the appid; global ignores it).
  const wScope: Scope = scope === "game" && game ? "game" : "global";
  const wTarget = wScope === "game" && game ? game.appid : null;

  const onEnable = useCallback((enabled: boolean) => {
    setAudioEnabled(enabled).then(setState).catch(() => {});
  }, []);

  const onPreset = useCallback((id: string) => {
    applyAudioPreset(id, wScope, wTarget).then(setState).catch(() => {});
  }, [wScope, wTarget]);

  const onBands = useCallback((gains: number[]) => {
    setState((cur) =>
      cur ? { ...cur, gains, preamp: computePreamp(gains), preset: "custom" } : cur,
    ); // optimistic — curve moves now, hardware settles on commit
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      setAudioBands(gains, wScope, wTarget).then(setState).catch(() => {});
    }, 350);
  }, [wScope, wTarget]);

  const onReset = useCallback(() => {
    resetAudio(wScope, wTarget).then(setState).catch(() => {});
  }, [wScope, wTarget]);

  return { state, scope, game, onScope, onEnable, onPreset, onBands, onReset };
}
