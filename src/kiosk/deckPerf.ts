import {
  applyPowerPreset,
  getPowerDraw,
  getPowerPresets,
  getTdpState,
  setAutoTdp,
  setAutoTdpConfig,
  setSeenAutotdpNotice,
  setTdpWatts,
  type PowerDraw,
  type PowerPresetState,
  type TdpScope,
  type TdpState,
} from "../api";
import { openAutoTdpNoticeModal } from "../components/AutoTdpNoticeModal";
import { effectiveEnabled } from "../customize/moduleLogic";
import { getDisabled } from "../customize/modules";
import { translate } from "../i18n";
import { resolveAutoView } from "../tdp/autoView";
import { monitorOnly } from "../tdp/conflict";
import { resolveLivePresets } from "../tdp/livePresets";
import { presetTitle, type PresetItem } from "../tdp/powerPresets";
import { readRunningGame } from "../tdp/runningGame";

/** What the native bottom screen shows for performance, resolved with the QAM's own rules. */
export interface DeckPerfView {
  ready: boolean;
  unit: string | null;
  levels: boolean;
  value: number | null;
  shown: number | null;
  min: number;
  max: number;
  autoReady: boolean;
  autoOn: boolean;
  target: number | null;
  maxFps: number | null;
  frequencies: TdpState["level_frequencies"] | null;
  presets: { id: string; title: string; icon: string; active: boolean }[];
}

export interface DeckPerfDeps {
  tdp: () => Promise<TdpState>;
  presets: () => Promise<PowerPresetState | null>;
  power: () => Promise<PowerDraw | null>;
  game: () => { appid: string } | null;
  autoModuleOn: () => boolean;
  t: (key: string, vars?: Record<string, string | number>) => string;
  confirmAutoNotice: (onConfirm: () => void, levels: boolean) => void;
  call: {
    applyPreset: typeof applyPowerPreset;
    setWatts: typeof setTdpWatts;
    setAuto: typeof setAutoTdp;
    setAutoConfig: typeof setAutoTdpConfig;
    seenNotice: typeof setSeenAutotdpNotice;
  };
}

interface Snapshot {
  tdp: TdpState;
  items: PresetItem[];
  view: DeckPerfView;
  scope: TdpScope;
  target: string | null;
  context: string | null;
}

export function createDeckPerf(deps: DeckPerfDeps) {
  const snapshot = async (): Promise<Snapshot> => {
    const [tdp, presets, power] = await Promise.all([
      deps.tdp(),
      deps.presets().catch(() => null),
      deps.power().catch(() => null),
    ]);
    const game = deps.game();
    const scope: TdpScope = game && !tdp.follows_global ? "game" : "global";
    const items = tdp.supported ? resolveLivePresets(tdp, presets, scope, deps.t).visible : [];
    const autoView = resolveAutoView(tdp, power, scope, Boolean(game));
    const ready = Boolean(tdp.supported) && !monitorOnly(Boolean(tdp.supported), tdp.tdp_control_enabled);
    const autoReady = ready && deps.autoModuleOn() && tdp.supports_auto_tdp !== false;
    const autoOn = autoReady && Boolean(autoView.config.enabled);
    const value = Math.round(scope === "global" ? tdp.global_watts : tdp.watts);
    const max = tdp.on_ac ? Math.max(tdp.limits.max, tdp.limits.max_ac) : tdp.limits.max;
    return {
      tdp,
      items,
      scope,
      target: scope === "game" && game ? game.appid : null,
      context: game?.appid ?? null,
      view: {
        ready,
        unit: tdp.unit ?? null,
        levels: tdp.unit === "level",
        value,
        shown: autoOn && power?.auto?.setpoint != null ? Math.round(power.auto.setpoint) : value,
        min: tdp.limits.min,
        max: Math.max(tdp.limits.min + 1, max),
        autoReady,
        autoOn,
        target: autoOn ? autoView.config.target_fps ?? null : null,
        maxFps: tdp.auto_target_max_fps ?? null,
        frequencies: tdp.level_frequencies ?? null,
        presets: items.map((item) => ({
          id: item.id,
          title: presetTitle(item, deps.t),
          icon: item.icon,
          active: item.active && !autoOn,
        })),
      },
    };
  };

  const enableAuto = (s: Snapshot) => {
    const on = () => deps.call.setAuto(true, s.scope, s.target, s.context);
    if (!s.tdp.seen_autotdp_notice) {
      deps.confirmAutoNotice(() => {
        void deps.call.seenNotice(true);
        void on();
      }, s.view.levels);
      return;
    }
    return on();
  };

  return {
    "perf.view": async () => (await snapshot()).view,
    "perf.preset": async ([id]: unknown[]) => {
      const s = await snapshot();
      const item = s.items.find((candidate) => candidate.id === id);
      if (!item || s.view.autoOn || !s.view.ready) throw new Error("unsupported");
      await deps.call.applyPreset(item.watts, s.scope, s.target, item.boost, s.context);
      return (await snapshot()).view;
    },
    "perf.level": async ([level]: unknown[]) => {
      const s = await snapshot();
      const value = Math.round(Number(level));
      if (!s.view.ready || s.view.autoOn || !Number.isFinite(value)) throw new Error("unsupported");
      await deps.call.setWatts(Math.max(s.view.min, Math.min(s.view.max, value)), s.scope, s.target, s.context);
      return (await snapshot()).view;
    },
    "perf.target": async ([fps]: unknown[]) => {
      const s = await snapshot();
      if (!s.view.autoReady) throw new Error("unsupported");
      if (fps == null) {
        if (s.view.autoOn) await deps.call.setAuto(false, s.scope, s.target, s.context);
        return (await snapshot()).view;
      }
      const config = s.scope === "global" ? s.tdp.global_auto_config : s.tdp.auto_config;
      await deps.call.setAutoConfig(
        Math.round(Number(fps)), config.initial_tdp, s.scope, s.target, s.context, config.min_tdp, config.max_tdp,
      );
      if (!s.view.autoOn) await enableAuto(s);
      return (await snapshot()).view;
    },
  };
}

export function steamDeckPerf() {
  return createDeckPerf({
    tdp: getTdpState,
    presets: getPowerPresets,
    power: getPowerDraw,
    game: readRunningGame,
    autoModuleOn: () => effectiveEnabled("autoTdp", new Set(getDisabled())),
    t: translate,
    confirmAutoNotice: (onConfirm, levels) => openAutoTdpNoticeModal({ onConfirm, onCancel: () => {}, levels }),
    call: {
      applyPreset: applyPowerPreset,
      setWatts: setTdpWatts,
      setAuto: setAutoTdp,
      setAutoConfig: setAutoTdpConfig,
      seenNotice: setSeenAutotdpNotice,
    },
  });
}
