import { useCallback, useEffect, useRef, useState } from "react";
import {
  getTdpState, setTdpWatts, setTdpLevels, setTdpBoostMode, setTdpFirmwareMode,
  getPowerDraw, setAutoTdp, setTdpFollowGlobal, setSeenAutotdpNotice,
  getPowerPresets, applyPowerPreset,
  TdpState, TdpScope, PowerDraw, BoostMode, PowerPresetState,
} from "../api";
import { PresetItem } from "./powerPresets";
import { openAutoTdpNoticeModal } from "../components/AutoTdpNoticeModal";
import { useRunningGame } from "./useRunningGame";
import { useScopeSync } from "../useScopeSync";

export interface TdpControl {
  tdp: TdpState | null;
  power: PowerDraw | null;
  scope: TdpScope;
  game: ReturnType<typeof useRunningGame>;
  refresh: () => void;
  onScope: (s: TdpScope) => void;
  onWatts: (w: number) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onSetMode: (mode: BoostMode) => void;
  onAutoTdpToggle: (enabled: boolean) => void;
  onFirmwareMode: (mode: string) => void;
  onApplySuggestion: (w: number) => void;
  // Custom power-preset library (order/hidden/custom); built-in watts come from `tdp`.
  presets: PowerPresetState | null;
  refreshPresets: () => void;
  onApplyPreset: (item: PresetItem) => void;
}

export function useTdp(): TdpControl {
  const game = useRunningGame();
  const [tdp, setTdp] = useState<TdpState | null>(null);
  const [power, setPower] = useState<PowerDraw | null>(null);
  const [presets, setPresets] = useState<PowerPresetState | null>(null);
  const commitTimerWatts = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitTimerLevels = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    getTdpState().then(setTdp).catch(() => {});
  }, []);

  const refreshPresets = useCallback(() => {
    getPowerPresets().then(setPresets).catch(() => {});
  }, []);
  useEffect(() => {
    refreshPresets();
  }, [refreshPresets]);

  // Re-fetch TDP on a charger flip so the ceiling (battery vs charger) updates.
  const lastAc = useRef<boolean | null>(null);
  useEffect(() => {
    const tick = () =>
      getPowerDraw()
        .then((p) => {
          setPower(p);
          if (lastAc.current !== null && lastAc.current !== p.on_ac) refresh();
          lastAc.current = p.on_ac;
        })
        .catch(() => {});
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [refresh]);

  const appid = game?.appid;
  useEffect(() => {
    refresh();
  }, [appid, refresh]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => { setTdpFollowGlobal(f, a).then(setTdp).catch(() => {}); },
    [],
  );
  const { scope, onScope } = useScopeSync(appid, tdp?.follows_global, applyFollow);

  const resolveTarget = useCallback((): { target: string | null; sc: TdpScope } => {
    const target = scope === "game" && game ? game.appid : null;
    return { target, sc: target ? "game" : "global" };
  }, [scope, game]);

  const onWatts = useCallback(
    (w: number) => {
      const { target, sc } = resolveTarget();
      setTdp((cur) =>
        cur ? { ...cur, watts: sc === "game" ? w : cur.watts, global_watts: sc === "global" ? w : cur.global_watts } : cur,
      );
      if (commitTimerWatts.current) clearTimeout(commitTimerWatts.current);
      commitTimerWatts.current = setTimeout(() => {
        setTdpWatts(w, sc, target).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [resolveTarget, refresh],
  );

  const onSetLevels = useCallback(
    (off2: number, off3: number) => {
      const { target, sc } = resolveTarget();
      setTdp((cur) => {
        if (!cur) return cur;
        const base = sc === "global" ? cur.global_levels : cur.levels;
        const nl = { pl1: base.pl1, pl2: base.pl1 + off2, pl3: base.pl1 + off2 + off3 };
        return sc === "global"
          ? { ...cur, global_levels: nl, global_boost_mode: "custom" }
          : { ...cur, levels: nl, boost_mode: "custom" };
      });
      if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
      commitTimerLevels.current = setTimeout(() => {
        setTdpLevels(off2, off3, sc, target).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [resolveTarget, refresh],
  );

  const onSetMode = useCallback((mode: BoostMode) => {
    const { target, sc } = resolveTarget();
    setTdpBoostMode(mode, sc, target).then(setTdp).catch(() => {});
  }, [resolveTarget]);

  const onAutoTdp = useCallback(
    (enabled: boolean) => {
      const { target, sc } = resolveTarget();
      setAutoTdp(enabled, sc, target).then(() => refresh()).catch(() => {});
    },
    [resolveTarget, refresh],
  );

  // First enable is gated behind the one-time notice; disabling isn't.
  const onAutoTdpToggle = useCallback(
    (enabled: boolean) => {
      if (enabled && tdp && !tdp.seen_autotdp_notice) {
        openAutoTdpNoticeModal({
          onConfirm: () => {
            setSeenAutotdpNotice(true).then(() => refresh()).catch(() => {});
            onAutoTdp(true);
          },
          onCancel: () => {},
        });
        return;
      }
      onAutoTdp(enabled);
    },
    [tdp, onAutoTdp, refresh],
  );

  const onFirmwareMode = useCallback((mode: string) => {
    setTdpFirmwareMode(mode).then(setTdp).catch(() => {});
  }, []);

  // Apply a preset chip: sustained watts (+ optional boost) to the current scope,
  // atomically server-side, then refresh so the arc/slider reflect it. Cancel any pending
  // debounced slider/levels write first, or its stale value would land after and override.
  const onApplyPreset = useCallback(
    (item: PresetItem) => {
      if (commitTimerWatts.current) clearTimeout(commitTimerWatts.current);
      if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
      const { target, sc } = resolveTarget();
      applyPowerPreset(item.watts, sc, target, item.boost).then(() => refresh()).catch(() => {});
    },
    [resolveTarget, refresh],
  );

  // A fixed PL1 is a distinct mode from dynamic auto-TDP → turn auto off first.
  const onApplySuggestion = useCallback(
    (w: number) => {
      const { target, sc } = resolveTarget();
      setAutoTdp(false, sc, target).then(() => setTdpWatts(w, sc, target)).then(() => refresh()).catch(() => {});
    },
    [resolveTarget, refresh],
  );

  return { tdp, power, scope, game, refresh, onScope, onWatts, onSetLevels, onSetMode, onAutoTdpToggle, onFirmwareMode, onApplySuggestion, presets, refreshPresets, onApplyPreset };
}
