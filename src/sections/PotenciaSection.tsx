import { FC, useCallback, useEffect, useRef, useState } from "react";
import { PanelSectionRow } from "@decky/ui";

import { getTdpState, setTdpWatts, setTdpLevels, setTdpBoostMode, setTdpFirmwareMode, getPowerDraw, setAutoTdp, setTdpFollowGlobal, setSeenAutotdpNotice, setSeenTdpConflictTakeover, TdpState, TdpScope, PowerDraw, BoostMode } from "../api";
import { TdpSection } from "../components/TdpSection";
import { GpuClockCard } from "../components/GpuClockCard";
import { AutoTdpToggle } from "../components/AutoTdpToggle";
import { TdpConflictCard } from "../components/TdpConflictCard";
import { openTdpConflictModal } from "../components/TdpConflictModal";
import { openAutoTdpNoticeModal } from "../components/AutoTdpNoticeModal";
import { SectionBlocks } from "../customize/SectionBlocks";
import { useLayout } from "../customize/store";
import { visibleIds } from "../customize/layout";
import { blockOrder } from "../customize/manifest";
import { useRunningGame } from "../tdp/useRunningGame";
import { useTdpConflict } from "../tdp/useTdpConflict";
import { useScopeSync } from "../useScopeSync";

/**
 * Power section: owns the TDP state (global/per-game scope, running game, the
 * debounced watt commit) and renders the power-arc UI. Relocated here from the
 * old single-panel index.tsx so the shell stays a dumb container and each
 * section owns its own state.
 */
export const PotenciaSection: FC = () => {
  const game = useRunningGame();
  const [tdp, setTdp] = useState<TdpState | null>(null);
  const [power, setPower] = useState<PowerDraw | null>(null);
  const commitTimerWatts = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitTimerLevels = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Fires the first-run take-over modal at most once per mount.
  const shownTakeover = useRef(false);
  // Reuse the state we already have so the hook doesn't re-fetch get_tdp_state.
  const conflict = useTdpConflict(tdp?.supported ?? false, tdp?.tdp_control_enabled ?? true);

  const refresh = useCallback(() => {
    getTdpState().then(setTdp).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll live power draw every second while the section is mounted.
  useEffect(() => {
    getPowerDraw().then(setPower).catch(() => {});
    const id = setInterval(() => {
      getPowerDraw().then(setPower).catch(() => {});
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const appid = game?.appid;
  useEffect(() => {
    refresh();
  }, [appid, refresh]);

  // The scope tab reflects the game's active profile and IS the control (shared wiring):
  // picking Global makes the running game follow the global profile, the game tab
  // activates its own, neither deletes the other.
  const applyFollow = useCallback(
    (f: boolean, a: string) => { setTdpFollowGlobal(f, a).then(setTdp).catch(() => {}); },
    [],
  );
  const { scope, onScope } = useScopeSync(appid, tdp?.follows_global, applyFollow);

  // Resolve the RPC target/scope from the current scope + running game. Falls
  // back to global when in game scope without a running game.
  const resolveTarget = useCallback((): { target: string | null; sc: TdpScope } => {
    const target = scope === "game" && game ? game.appid : null;
    return { target, sc: target ? "game" : "global" };
  }, [scope, game]);

  const onWatts = useCallback(
    (w: number) => {
      const { target, sc } = resolveTarget();
      setTdp((cur) =>
        cur
          ? {
              ...cur,
              watts: sc === "game" ? w : cur.watts,
              global_watts: sc === "global" ? w : cur.global_watts,
            }
          : cur,
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

  // The RPC returns the full new state so the segmented control + rails update
  // together in one round-trip (no transient mode/rail mismatch).
  const onSetMode = useCallback((mode: BoostMode) => {
    const { target, sc } = resolveTarget();
    setTdpBoostMode(mode, sc, target).then(setTdp).catch(() => {});
  }, [resolveTarget]);

  const onAutoTdp = useCallback(
    (enabled: boolean) => {
      const { target, sc } = resolveTarget();
      setAutoTdp(enabled, sc, target)
        .then(() => refresh())
        .catch(() => {});
    },
    [resolveTarget, refresh],
  );

  // Gate the first enable of Auto‑TDP behind the one-time notice. Disabling isn't gated.
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

  // Firmware performance mode (Legion Go original). Device-global; the RPC returns the
  // full new state so the arc + chips update in one round-trip.
  const onFirmwareMode = useCallback((mode: string) => {
    setTdpFirmwareMode(mode).then(setTdp).catch(() => {});
  }, []);

  // Apply the learned-band suggestion: a FIXED PL1 at the dial-picked value, which is
  // a distinct mode from dynamic auto-TDP → turn auto OFF, then commit the watts to the
  // current scope. Refresh so the slider/arc reflect the new fixed setpoint.
  const onApplySuggestion = useCallback(
    (w: number) => {
      const { target, sc } = resolveTarget();
      setAutoTdp(false, sc, target)
        .then(() => setTdpWatts(w, sc, target))
        .then(() => refresh())
        .catch(() => {});
    },
    [resolveTarget, refresh],
  );

  // The fixed TDP core (arc + slider/presets) renders first; the GPU-clock card
  // and the Auto‑TDP toggle are reorderable/hideable blocks below it — GPU before
  // Auto‑TDP by default (see the "power" entry in the customization manifest).
  const isAutoOn = power?.auto_tdp ?? false;

  // Safety: if the Auto‑TDP block is hidden while auto is ON, there's no way to
  // turn it off from Potencia (the core shows the live gauge, no slider). So
  // hiding it disables auto-TDP — the loop's last PL1 stays as a fixed, editable
  // value. onAutoTdp(false) is idempotent; this fires once when it becomes hidden.
  const layout = useLayout();
  const autoTdpVisible = visibleIds(blockOrder("power"), layout.blocks["power"]).includes("autoTdp");
  useEffect(() => {
    if (!autoTdpVisible && isAutoOn) onAutoTdp(false);
  }, [autoTdpVisible, isAutoOn, onAutoTdp]);

  // Keep the latest conflict actions reachable from the modal callback without
  // re-arming the first-run effect.
  const conflictRef = useRef(conflict);
  conflictRef.current = conflict;

  // First-run take-over: pop the modal once when a live conflict first appears, then
  // persist the flag. After that the persistent card handles it.
  useEffect(() => {
    if (!tdp || shownTakeover.current) return;
    if (conflict.conflict && !tdp.seen_tdp_conflict_takeover) {
      shownTakeover.current = true;
      openTdpConflictModal(() => void conflictRef.current.takeAll());
      setSeenTdpConflictTakeover(true).then(() => refresh()).catch(() => {});
    }
  }, [conflict.conflict, tdp, refresh]);

  return (
    <>
      {conflict.conflict && (
        <PanelSectionRow>
          <TdpConflictCard
            rivals={conflict.rivals}
            onDisableSdtdp={() => void conflict.disableSdtdp()}
            onTakeHhd={() => void conflict.takeHhd()}
          />
        </PanelSectionRow>
      )}
      <TdpSection
        tdp={tdp}
        scope={scope}
        game={game}
        power={power}
        onScope={onScope}
        onWatts={onWatts}
        onSetLevels={onSetLevels}
        onSetMode={onSetMode}
        onApplySuggestion={onApplySuggestion}
        onFirmwareMode={onFirmwareMode}
        monitorOnly={conflict.monitorOnly}
      />
      {/* Every write control drops away in monitor-only mode (we've stepped aside). */}
      {!conflict.monitorOnly && (
        <SectionBlocks
          sectionId="power"
          blocks={{
            gpu: <GpuClockCard scope={scope} appid={game?.appid ?? null} />,
            autoTdp: <AutoTdpToggle checked={isAutoOn} onChange={onAutoTdpToggle} />,
          }}
        />
      )}
    </>
  );
};
