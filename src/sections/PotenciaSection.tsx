import { FC, useCallback, useEffect, useRef, useState } from "react";

import { getTdpState, setTdpWatts, setTdpLevels, resetTdpAuto, TdpState, TdpScope } from "../api";
import { TdpSection } from "../components/TdpSection";
import { useRunningGame } from "../tdp/useRunningGame";

/**
 * Power section: owns the TDP state (global/per-game scope, running game, the
 * debounced watt commit) and renders the power-arc UI. Relocated here from the
 * old single-panel index.tsx so the shell stays a dumb container and each
 * section owns its own state.
 */
export const PotenciaSection: FC = () => {
  const game = useRunningGame();
  const [tdp, setTdp] = useState<TdpState | null>(null);
  const [scope, setScope] = useState<TdpScope>("global");
  const commitTimerWatts = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitTimerLevels = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    getTdpState().then(setTdp).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const appid = game?.appid;
  useEffect(() => {
    setScope(appid ? "game" : "global");
    refresh();
  }, [appid, refresh]);

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
          ? { ...cur, global_levels: nl, global_auto: false }
          : { ...cur, levels: nl, auto: false };
      });
      if (commitTimerLevels.current) clearTimeout(commitTimerLevels.current);
      commitTimerLevels.current = setTimeout(() => {
        setTdpLevels(off2, off3, sc, target).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [resolveTarget, refresh],
  );

  const onResetAuto = useCallback(() => {
    const { target, sc } = resolveTarget();
    setTdp((cur) =>
      cur
        ? sc === "global"
          ? { ...cur, global_auto: true }
          : { ...cur, auto: true }
        : cur,
    );
    resetTdpAuto(sc, target).then(() => refresh()).catch(() => {});
  }, [resolveTarget, refresh]);

  return (
    <TdpSection
      tdp={tdp}
      scope={scope}
      game={game}
      onScope={setScope}
      onWatts={onWatts}
      onSetLevels={onSetLevels}
      onResetAuto={onResetAuto}
    />
  );
};
