import { FC, useCallback, useEffect, useRef, useState } from "react";

import { getTdpState, setTdpWatts, TdpState, TdpScope } from "../api";
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
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const onWatts = useCallback(
    (w: number) => {
      setTdp((cur) =>
        cur
          ? {
              ...cur,
              watts: scope === "game" ? w : cur.watts,
              global_watts: scope === "global" ? w : cur.global_watts,
            }
          : cur,
      );
      if (commitTimer.current) clearTimeout(commitTimer.current);
      const target = scope === "game" && game ? game.appid : null;
      commitTimer.current = setTimeout(() => {
        setTdpWatts(w, scope, target).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [scope, game, refresh],
  );

  return (
    <TdpSection tdp={tdp} scope={scope} game={game} onScope={setScope} onWatts={onWatts} />
  );
};
