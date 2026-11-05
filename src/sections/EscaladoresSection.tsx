import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useState, type FC } from "react";

import { getUpscalersCompat, getUpscalersOverview, type GameCompat } from "../api";
import { FocusableCard } from "../components/FocusableCard";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import { listInstalledGames, type GameEntry } from "../launch/steamApi";
import { onUpscalersGameRequest, takePendingUpscalersGame } from "../upscalers/deepLink";
import { theme } from "../theme";
import { BulkPanel } from "../upscalers/BulkPanel";
import { GameView } from "../upscalers/GameView";
import { IN_GAME_MODES, publishOverview, readInGameMode, setUpscalersSectionOpen, writeInGameMode, type InGameMode } from "../upscalers/overlays";
import { Label, SegmentRow } from "../upscalers/parts";
import { buildLabel } from "../upscalers/model";
import { Dot, MOTION_CSS, Skeleton, statusColor } from "../upscalers/parts";
import { showGame, takeHeldPage, type PageDraft } from "../upscalers/pageMemory";
import type { UpscalerChoice, UpscalersOverview } from "../upscalers/types";

export const EscaladoresSection: FC = () => {
  const { t } = useI18n();
  const [overview, setOverview] = useState<UpscalersOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [held] = useState(takeHeldPage);
  const [selected, setSelected] = useState<GameEntry | null>(() => held ? listInstalledGames().find((g) => g.liveAppid === held.appid) ?? null : null);
  const [compat, setCompat] = useState<Record<string, GameCompat>>({});
  const [inGame, setInGame] = useState<InGameMode>(readInGameMode);

  const refresh = useCallback(async () => {
    try {
      const next = await getUpscalersOverview();
      setOverview(next);
      publishOverview(next);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    setUpscalersSectionOpen(true);
    return () => setUpscalersSectionOpen(false);
  }, []);
  const closeGame = useCallback(() => {
    showGame(null);
    setSelected(null);
  }, []);

  useEffect(() => {
    const open = () => {
      const appid = takePendingUpscalersGame();
      const game = appid === null ? null : listInstalledGames().find((g) => g.liveAppid === appid);
      if (game) setSelected(game);
    };
    open();
    return onUpscalersGameRequest(open);
  }, []);

  const games = useMemo(() => {
    const installs = overview?.installs ?? {};
    return listInstalledGames()
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
        <GameView game={selected} overview={overview} onBack={closeGame} onChanged={refresh}
          draft={held?.appid === selected.liveAppid ? held.draft as PageDraft<UpscalerChoice> | null : null} />
      ) : (
        <>
          {failed && <span style={{ fontSize: theme.font.caption }}>{t("load.error")}</span>}
          {!overview && !failed && [0, 1, 2, 3].map((i) => <Skeleton key={i} height={64} />)}
          {overview && (
            <>
              <Label>{t("up.inGame.title")}</Label>
              <SegmentRow
                value={inGame}
                onChange={(mode) => { setInGame(mode); writeInGameMode(mode); }}
                options={IN_GAME_MODES.map((mode) => ({ value: mode, label: t(`up.inGame.${mode}`) }))}
              />
              <BulkPanel games={games} overview={overview} compat={compat} onChanged={() => void refresh()} />
              <Label>{t("up.games")}</Label>
            </>
          )}
          {overview && games.length === 0 && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.empty")}</span>
          )}
          {overview && games.map((game) => {
            const install = overview.installs[String(game.liveAppid)];
            const build = install && overview.builds.find((b) => b.id === install.build);
            const busy = overview.job?.state === "running" && overview.job.appid === String(game.liveAppid);
            const info = compat[String(game.liveAppid)];
            return (
              <FocusableCard key={game.instanceKey} onActivate={() => setSelected(game)}>
                <GameCover urls={game.coverUrls} name={game.name} width={30} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {game.name}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, marginTop: 2, minHeight: 16 }}>
                    {install ? (
                      <>
                        <Dot color={statusColor(install.status)} />
                        <span style={{ color: theme.color.textPrimary }}>{build ? buildLabel(build) : install.build}</span>
                      </>
                    ) : info ? (
                      <span style={{ color: info.inputs.length ? theme.color.ok : theme.color.textMuted }}>
                        {info.native ? t("up.list.linux") : info.inputs.length ? info.inputs.join(", ") : t("up.list.none")}
                      </span>
                    ) : null}
                  </div>
                  {busy && <div style={{ fontSize: theme.font.caption, color: theme.color.accent }}>{t("up.phase.prepare")}</div>}
                </div>
              </FocusableCard>
            );
          })}
        </>
      )}
    </Focusable>
  );
};
