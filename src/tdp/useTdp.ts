import { useCallback, useEffect, useRef, useState } from "react";
import {
  getTdpState, setTdpWatts, setTdpLevels, setTdpBoostMode, setTdpFirmwareMode,
  getPowerDraw, setAutoTdp, setTdpFollowGlobal, setSeenAutotdpNotice,
  setLowBatteryTdpHold, getPowerPresets, applyPowerPreset, setAutoTdpConfig,
  TdpState, TdpScope, PowerDraw, BoostMode, PowerPresetState, AutoTdpConfig,
} from "../api";
import { PresetItem } from "./powerPresets";
import { openAutoTdpNoticeModal } from "../components/AutoTdpNoticeModal";
import { useRunningGame } from "./useRunningGame";
import { useScopeSync } from "../useScopeSync";
import { notifyLearningStatusChanged } from "../learning/statusInvalidation";
import { effectiveAutoRange } from "./autoView";

const RECOVERY_RETRY_DELAYS_MS = [2000, 4000, 8000] as const;

interface AutoDraft {
  context: string | null;
  config: AutoTdpConfig;
  timer: ReturnType<typeof setTimeout> | null;
  confirmed: boolean;
}

type AutoDrafts = Partial<Record<TdpScope, AutoDraft>>;

function confirmedAutoDrafts(drafts: AutoDrafts): AutoDrafts {
  return {
    global: drafts.global?.confirmed ? drafts.global : undefined,
    game: drafts.game?.confirmed ? drafts.game : undefined,
  };
}

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
  onAutoTargetFps: (fps: number) => void;
  onAutoInitialTdp: (watts: number) => void;
  onAutoMinTdp: (watts: number) => void;
  onAutoMaxTdp: (watts: number) => void;
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
  const autoDrafts = useRef<AutoDrafts>({});
  const followEpoch = useRef(0);

  const reconcileAutoState = useCallback((next: TdpState, confirmed: AutoDrafts): TdpState => {
    let updated = next;
    for (const sc of ["global", "game"] as const) {
      if (sc === "game" && next.follows_global) continue;
      const draft = autoDrafts.current[sc];
      if (!draft) continue;
      if (draft === confirmed[sc]) {
        const field = sc === "global" ? "global_auto_config" : "auto_config";
        autoDrafts.current[sc] = { ...draft, config: next[field] };
      } else {
        const field = sc === "global" ? "global_auto_config" : "auto_config";
        updated = { ...updated, [field]: { ...draft.config, enabled: next[field].enabled } };
      }
    }
    return updated.follows_global
      ? { ...updated, auto_config: updated.global_auto_config }
      : updated;
  }, []);

  const refresh = useCallback(() => {
    const confirmed = confirmedAutoDrafts(autoDrafts.current);
    const epoch = followEpoch.current;
    getTdpState().then((next) => {
      if (epoch !== followEpoch.current) return;
      setTdp(reconcileAutoState(next, confirmed));
    }).catch(() => {});
  }, [reconcileAutoState]);

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
    for (const draft of Object.values(autoDrafts.current)) {
      if (draft.timer) clearTimeout(draft.timer);
    }
    commitTimerWatts.current = null;
    commitTimerLevels.current = null;
    autoDrafts.current = {};
    followEpoch.current += 1;
  }, [appid]);

  const applyFollow = useCallback(
    (f: boolean, a: string) => {
      if (f && tdp && !tdp.follows_global && !autoDrafts.current.game) {
        autoDrafts.current.game = { context: a, config: tdp.auto_config, timer: null, confirmed: true };
      }
      const epoch = ++followEpoch.current;
      const confirmed = confirmedAutoDrafts(autoDrafts.current);
      return setTdpFollowGlobal(f, a, a)
        .then((next) => {
          if (epoch !== followEpoch.current) return true;
          setTdp(reconcileAutoState(next, confirmed));
          return next.follows_global === f;
        })
        .catch(() => false);
    },
    [reconcileAutoState, tdp],
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
      setAutoTdp(enabled, sc, target, context)
        .then(() => {
          notifyLearningStatusChanged();
          refresh();
        })
        .catch(() => {});
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

  const onAutoConfig = useCallback((next: {
    target_fps?: number;
    initial_tdp?: number;
    min_tdp?: number;
    max_tdp?: number;
  }) => {
    const { target, sc, context } = resolveTarget();
    const selected = sc === "global" ? tdp?.global_auto_config : tdp?.auto_config;
    if (!selected || !tdp) return;
    const pending = autoDrafts.current[sc];
    const config = {
      ...(pending?.context === context ? pending.config : selected),
      ...next,
    };
    if (next.min_tdp !== undefined && next.min_tdp > (config.max_tdp ?? tdp.auto_request_limits.max_ac)) {
      config.max_tdp = next.min_tdp;
    }
    if (next.max_tdp !== undefined && next.max_tdp < (config.min_tdp ?? tdp.auto_request_limits.min)) {
      config.min_tdp = next.max_tdp;
    }
    if (next.initial_tdp !== undefined || next.min_tdp !== undefined || next.max_tdp !== undefined) {
      const range = effectiveAutoRange(config, tdp.auto_limits, tdp.on_ac);
      config.initial_tdp = Math.max(range.min, Math.min(config.initial_tdp, range.max));
    }
    const draft: AutoDraft = { context, config, timer: null, confirmed: false };
    autoDrafts.current[sc] = draft;
    setTdp((current) => {
      if (!current) return current;
      return sc === "global"
        ? { ...current, global_auto_config: config, ...(current.follows_global ? { auto_config: config } : {}) }
        : current.follows_global ? current : { ...current, auto_config: config };
    });
    if (pending?.timer) clearTimeout(pending.timer);
    draft.timer = setTimeout(() => {
      draft.timer = null;
      setAutoTdpConfig(
        config.target_fps,
        config.initial_tdp,
        sc,
        target,
        context,
        config.min_tdp,
        config.max_tdp,
      ).then((updated) => {
        if (autoDrafts.current[sc] !== draft) return;
        const field = sc === "global" ? "global_auto_config" : "auto_config";
        if (sc === "global" || !updated.follows_global) draft.config = updated[field];
        draft.confirmed = true;
        setTdp((current) => {
          if (!current || (sc === "game" && current.follows_global)) return current;
          return {
            ...current,
            [field]: draft.config,
            ...(sc === "global" && current.follows_global ? { auto_config: draft.config } : {}),
          };
        });
      }).catch(() => {
        if (autoDrafts.current[sc] !== draft) return;
        delete autoDrafts.current[sc];
        refresh();
      });
    }, 200);
  }, [resolveTarget, refresh, tdp]);

  const onAutoTargetFps = useCallback(
    (fps: number) => onAutoConfig({ target_fps: fps }),
    [onAutoConfig],
  );
  const onAutoInitialTdp = useCallback(
    (watts: number) => onAutoConfig({ initial_tdp: watts }),
    [onAutoConfig],
  );
  const onAutoMinTdp = useCallback(
    (watts: number) => onAutoConfig({ min_tdp: watts }),
    [onAutoConfig],
  );
  const onAutoMaxTdp = useCallback(
    (watts: number) => onAutoConfig({ max_tdp: watts }),
    [onAutoConfig],
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

  return {
    tdp,
    power,
    scope,
    game,
    refresh,
    onScope,
    onWatts,
    onSetLevels,
    onSetMode,
    onAutoTdpToggle,
    onAutoTargetFps,
    onAutoInitialTdp,
    onAutoMinTdp,
    onAutoMaxTdp,
    onFirmwareMode,
    onLowBatteryHold,
    onApplySuggestion,
    presets,
    refreshPresets,
    onApplyPreset,
  };
}
