import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useState, type FC } from "react";

import { getUpscalersCompat, getUpscalersOverview } from "../api";
import { FocusableCard } from "../components/FocusableCard";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import { listInstalledGames, type GameEntry } from "../launch/steamApi";
import { theme } from "../theme";
import { GameView } from "../upscalers/GameView";
import { buildLabel } from "../upscalers/model";
import { Dot, MOTION_CSS, Skeleton, statusColor } from "../upscalers/parts";
import type { UpscalersOverview } from "../upscalers/types";

export const EscaladoresSection: FC = () => {
  const { t } = useI18n();
  const [overview, setOverview] = useState<UpscalersOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<GameEntry | null>(null);
  const [compat, setCompat] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    try {
      setOverview(await getUpscalersOverview());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const games = useMemo(() => {
    const installs = overview?.installs ?? {};
    return listInstalledGames()
      .filter((g) => !g.isNonSteam)
      .sort((a, b) => Number(String(b.liveAppid) in installs) - Number(String(a.liveAppid) in installs) || b.lastPlayed - a.lastPlayed);
  }, [overview]);

  const appids = games.map((g) => String(g.liveAppid)).join(",");
  useEffect(() => {
    if (!appids) return;
    let alive = true;
    getUpscalersCompat(appids.split(",")).then((next) => { if (alive) setCompat(next); }).catch(() => undefined);
    return () => { alive = false; };
  }, [appids]);

  return (
    <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <style>{MOTION_CSS}</style>
      {selected && overview ? (
        <GameView game={selected} overview={overview} onBack={() => setSelected(null)} onChanged={() => void refresh()} />
      ) : (
        <>
          {failed && <span style={{ fontSize: theme.font.caption }}>{t("load.error")}</span>}
          {!overview && !failed && [0, 1, 2, 3].map((i) => <Skeleton key={i} height={64} />)}
          {overview && games.length === 0 && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.empty")}</span>
          )}
          {overview && games.map((game) => {
            const install = overview.installs[String(game.liveAppid)];
            const build = install && overview.builds.find((b) => b.id === install.build);
            const busy = overview.job?.state === "running" && overview.job.appid === String(game.liveAppid);
            return (
              <FocusableCard key={game.instanceKey} onActivate={() => setSelected(game)}>
                <GameCover urls={game.coverUrls} name={game.name} width={30} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {game.name}
                  </div>
                  {install && (
                    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, marginTop: 2 }}>
                      <Dot color={statusColor(install.status)} />
                      <span style={{ color: theme.color.textMuted }}>{build ? buildLabel(build) : install.build}</span>
                    </div>
                  )}
                  {busy && <div style={{ fontSize: theme.font.caption, color: theme.color.accent }}>{t("up.phase.prepare")}</div>}
                </div>
                {!install && compat[String(game.liveAppid)] && (
                  <span style={{
                    fontSize: theme.font.caption, fontWeight: 600, padding: "2px 8px", borderRadius: 999,
                    color: theme.color.ok, boxShadow: `inset 0 0 0 1px ${theme.color.ok}66`, flexShrink: 0,
                  }}>
                    {t("up.compatible")}
                  </span>
                )}
              </FocusableCard>
            );
          })}
        </>
      )}
    </Focusable>
  );
};
