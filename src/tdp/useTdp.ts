import { useCallback, useEffect, useRef, useState } from "react";
import {
  getTdpState, setTdpWatts, setTdpLevels, setTdpBoostMode, setTdpFirmwareMode,
  getPowerDraw, setAutoTdp, setTdpFollowGlobal, setSeenAutotdpNotice,
  setLowBatteryTdpHold,
  getPowerPresets, applyPowerPreset,
  TdpState, TdpScope, PowerDraw, BoostMode, PowerPresetState,
} from "../api";
import { PresetItem } from "./powerPresets";
import { openAutoTdpNoticeModal } from "../components/AutoTdpNoticeModal";
import { useRunningGame } from "./useRunningGame";
import { useScopeSync } from "../useScopeSync";

const RECOVERY_RETRY_DELAYS_MS = [2000, 4000, 8000] as const;

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
  onLowBatteryHold: (enabled: boolean) => void;
  onApplySuggestion: (w: number) => void;
  // Custom power-preset library (order/hidden/custom); built-in watts come from `tdp`.
  presets: PowerPresetState | null;
  refreshPresets: () => void;
  onApplyPreset: (item: PresetItem) => void;
}

function levelsAtWatts(levels: TdpState["levels"], watts: number, mode: BoostMode): TdpState["levels"] {
  if (mode === "estable") return { pl1: watts, pl2: watts, pl3: watts };
  if (mode === "auto") {
    return { pl1: watts, pl2: Math.round(watts * 1.2), pl3: Math.round(watts * 1.4) };
  }
  const off2 = Math.max(0, levels.pl2 - levels.pl1);
  const off3 = Math.max(0, levels.pl3 - levels.pl2);
  return { pl1: watts, pl2: watts + off2, pl3: watts + off2 + off3 };
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
  useEffect(() => {
    if (!tdp?.recovery_pending) return;
    let cancelled = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const retry = () => {
      const delay = RECOVERY_RETRY_DELAYS_MS[attempts];
      if (delay === undefined) return;
      timer = setTimeout(() => {
        attempts += 1;
        getTdpState()
          .then((next) => {
            if (cancelled) return;
            setTdp(next);
            if (next.recovery_pending) retry();
          })
          .catch(() => {
            if (!cancelled) retry();
          });
      }, delay);
    };
    retry();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [tdp?.recovery_pending]);

  // Re-fetch TDP on a charger flip so the ceiling (battery vs charger) updates.
  const lastAc = useRef<boolean | null>(null);
  useEffect(() => {
    const tick = () =>
      getPowerDraw()
        .then((p) => {
          setPower(p);
          setTdp((current) =>
            current ? { ...current, ownership: p.ownership } : current
          );
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
  useEffect(() => () => {
    if (commitTimerWatts.current) clearTimeout(commitTimerWatts.current);
    if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
    commitTimerWatts.current = null;
    commitTimerLevels.current = null;
  }, [appid]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => setTdpFollowGlobal(f, a, a)
      .then((next) => {
        setTdp(next);
        return next.follows_global === f;
      })
      .catch(() => false),
    [],
  );
  const { scope, onScope } = useScopeSync(appid, tdp?.follows_global, applyFollow);

  const resolveTarget = useCallback((): {
    target: string | null;
    sc: TdpScope;
    context: string | null;
  } => {
    const target = scope === "game" && game ? game.appid : null;
    return {
      target,
      sc: target ? "game" : "global",
      context: game?.appid ?? null,
    };
  }, [scope, game]);

  const onWatts = useCallback(
    (w: number) => {
      const { target, sc, context } = resolveTarget();
      setTdp((cur) => {
        if (!cur) return cur;
        if (sc === "global") {
          const levels = cur.global_requested_levels ?? cur.global_levels;
          return {
            ...cur,
            global_watts: w,
            global_requested_levels: levelsAtWatts(levels, w, cur.global_boost_mode),
          };
        }
        const levels = cur.requested_levels ?? cur.levels;
        return {
          ...cur,
          watts: w,
          requested_levels: levelsAtWatts(levels, w, cur.boost_mode),
        };
      });
      if (commitTimerWatts.current) clearTimeout(commitTimerWatts.current);
      commitTimerWatts.current = setTimeout(() => {
        setTdpWatts(w, sc, target, context).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [resolveTarget, refresh],
  );

  const onSetLevels = useCallback(
    (off2: number, off3: number) => {
      const { target, sc, context } = resolveTarget();
      setTdp((cur) => {
        if (!cur) return cur;
        const base = sc === "global"
          ? (cur.global_requested_levels ?? cur.global_levels)
          : (cur.requested_levels ?? cur.levels);
        const nl = { pl1: base.pl1, pl2: base.pl1 + off2, pl3: base.pl1 + off2 + off3 };
        return sc === "global"
          ? { ...cur, global_requested_levels: nl, global_boost_mode: "custom" }
          : { ...cur, requested_levels: nl, boost_mode: "custom" };
      });
      if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
      commitTimerLevels.current = setTimeout(() => {
        setTdpLevels(off2, off3, sc, target, context).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [resolveTarget, refresh],
  );

  const onSetMode = useCallback((mode: BoostMode) => {
    const { target, sc, context } = resolveTarget();
    setTdpBoostMode(mode, sc, target, context).then(setTdp).catch(() => {});
  }, [resolveTarget]);

  const onAutoTdp = useCallback(
    (enabled: boolean) => {
      const { target, sc, context } = resolveTarget();
      setAutoTdp(enabled, sc, target, context).then(() => refresh()).catch(() => {});
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

  const onLowBatteryHold = useCallback((enabled: boolean) => {
    return setLowBatteryTdpHold(enabled).then(setTdp).catch(() => {});
  }, []);

  // Apply a preset chip: sustained watts (+ optional boost) to the current scope,
  // atomically server-side, then refresh so the arc/slider reflect it. Cancel any pending
  // debounced slider/levels write first, or its stale value would land after and override.
  const onApplyPreset = useCallback(
    (item: PresetItem) => {
      if (commitTimerWatts.current) clearTimeout(commitTimerWatts.current);
      if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
      const { target, sc, context } = resolveTarget();
      applyPowerPreset(item.watts, sc, target, item.boost, context).then(() => refresh()).catch(() => {});
    },
    [resolveTarget, refresh],
  );

  // A fixed PL1 is a distinct mode from dynamic auto-TDP → turn auto off first.
  const onApplySuggestion = useCallback(
    (w: number) => {
      const { target, sc, context } = resolveTarget();
      setAutoTdp(false, sc, target, context)
        .then(() => setTdpWatts(w, sc, target, context))
        .then(() => refresh())
        .catch(() => {});
    },
    [resolveTarget, refresh],
  );

  return { tdp, power, scope, game, refresh, onScope, onWatts, onSetLevels, onSetMode, onAutoTdpToggle, onFirmwareMode, onLowBatteryHold, onApplySuggestion, presets, refreshPresets, onApplyPreset };
}
