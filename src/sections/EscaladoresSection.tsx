import { LuCircleCheck, LuClock, LuSlidersHorizontal, LuTriangleAlert } from "react-icons/lu";
import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useState, type FC, type ComponentProps } from "react";

import { getUpscalersCompat, getUpscalersOverview, type GameCompat } from "../api";
import { FocusableCard } from "../components/FocusableCard";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import { listInstalledGames, type GameEntry } from "../launch/steamApi";
import { onUpscalersGameRequest, takePendingUpscalersGame } from "../upscalers/deepLink";
import { theme } from "../theme";
import { BulkPanel } from "../upscalers/BulkPanel";
import { GameView } from "../upscalers/GameView";
import { IN_GAME_MODES, publishOverview, readCoverBadges, readInGameMode, setUpscalersSectionOpen, writeCoverBadges, writeInGameMode, type InGameMode } from "../upscalers/overlays";
import { Fold, Label, SegmentRow } from "../upscalers/parts";
import { badgeLabel } from "../upscalers/model";
import { MOTION_CSS, Skeleton, statusColor } from "../upscalers/parts";
import { showGame, takeHeldPage, type PageDraft } from "../upscalers/pageMemory";
import type { UpscalerChoice, UpscalersOverview } from "../upscalers/types";

const NavigationGroup = Focusable as FC<ComponentProps<typeof Focusable> & { childFocusDisabled?: boolean }>;

export const EscaladoresSection: FC = () => {
  const { t } = useI18n();
  const [overview, setOverview] = useState<UpscalersOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [held] = useState(takeHeldPage);
  const [selected, setSelected] = useState<GameEntry | null>(() => held ? listInstalledGames().find((g) => g.liveAppid === held.appid) ?? null : null);
  const [compat, setCompat] = useState<Record<string, GameCompat>>({});
  const [compatRead, setCompatRead] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [inGame, setInGame] = useState<InGameMode>(readInGameMode);
  const [coversOpen, setCoversOpen] = useState(false);
  const [covers, setCovers] = useState(readCoverBadges);

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
    const ids = appids.split(",");
    // The backend answers at most 400 games per call; a whole store library can be longer.
    const batches = Array.from({ length: Math.ceil(ids.length / 400) }, (_, index) => ids.slice(index * 400, index * 400 + 400));
    Promise.all(batches.map((batch) => getUpscalersCompat(batch).catch(() => ({}))))
      .then((parts) => { if (alive) setCompat(Object.assign({}, ...parts)); })
      .finally(() => { if (alive) setCompatRead(true); });
    return () => { alive = false; };
  }, [appids]);
  // Store shortcuts with no installed game behind them (Unifideck lists a whole library) have nothing to scale.
  // Shortcuts wait for that answer, so a library-only entry never shows up and then vanishes under the focus.
  const listed = useMemo(() => games.filter((g) => compatRead ? !compat[String(g.liveAppid)]?.unavailable : !g.isNonSteam),
    [games, compat, compatRead]);

  return (
    <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <style>{MOTION_CSS}</style>
      {selected && overview ? (
        <GameView key={selected.liveAppid} game={selected} overview={overview} onBack={closeGame} onChanged={refresh}
          draft={held?.appid === selected.liveAppid ? held.draft as PageDraft<UpscalerChoice> | null : null} />
      ) : (
        <>
          {failed && <span style={{ fontSize: theme.font.caption }}>{t("load.error")}</span>}
          {!overview && !failed && [0, 1, 2, 3].map((i) => <Skeleton key={i} height={64} />)}
          {overview && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <Label>{t("up.games")}</Label>
                <Focusable role="button" aria-expanded={optionsOpen} onActivate={() => setOptionsOpen(!optionsOpen)} onClick={() => setOptionsOpen(!optionsOpen)}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: 8, color: theme.color.textPrimary, fontSize: theme.font.caption }}>
                  <LuSlidersHorizontal size={16} />{t("up.list.options")}
                </Focusable>
              </div>
              <NavigationGroup flow-children="column" childFocusDisabled={!optionsOpen} aria-hidden={!optionsOpen} style={{ display: optionsOpen ? "flex" : "none", flexDirection: "column", gap: theme.space.xs }}>
                <Fold label={t("up.inGame.title")} open={noticeOpen} onToggle={() => setNoticeOpen(!noticeOpen)} />
                {noticeOpen && <SegmentRow
                  value={inGame}
                  onChange={(mode) => { setInGame(mode); writeInGameMode(mode); }}
                  options={IN_GAME_MODES.map((mode) => ({ value: mode, label: t(`up.inGame.${mode}`) }))}
                />}
                <Fold label={t("up.covers.title")} open={coversOpen} onToggle={() => setCoversOpen(!coversOpen)} />
                {coversOpen && <SegmentRow
                  value={covers ? "on" : "off"}
                  onChange={(value) => { setCovers(value === "on"); writeCoverBadges(value === "on"); }}
                  options={(["on", "off"] as const).map((value) => ({ value, label: t(`up.covers.${value}`) }))}
                />}
                <Fold label={t("up.list.manage")} open={bulkOpen} onToggle={() => setBulkOpen(!bulkOpen)} />
                <NavigationGroup flow-children="column" childFocusDisabled={!bulkOpen} aria-hidden={!bulkOpen} style={{ display: bulkOpen ? "flex" : "none", flexDirection: "column", gap: theme.space.xs }}>
                  <BulkPanel games={listed} overview={overview} compat={compat} onChanged={() => void refresh()} />
                </NavigationGroup>
              </NavigationGroup>
              <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm, fontSize: theme.font.caption, color: theme.color.textMuted, paddingBottom: 4 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><LuCircleCheck color={theme.color.ok} />{t("up.list.checked")}</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><LuClock color={theme.color.accent} />{t("up.list.unchecked")}</span>
              </div>
            </>
          )}
          {overview && listed.length === 0 && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.empty")}</span>
          )}
          {overview && listed.map((game) => {
            const install = overview.installs[String(game.liveAppid)];
            const build = install && overview.builds.find((b) => b.id === install.build);
            const busy = overview.job?.state === "running" && overview.job.appid === String(game.liveAppid);
            const info = compat[String(game.liveAppid)];
            const engines = overview.engines?.[String(game.liveAppid)];
            const frameGen = engines?.mako?.fg ? `Mako${engines.mako.multiplier ? ` ×${engines.mako.multiplier}` : ""}`
              : engines?.lossless ? `Lossless${engines.lossless.multiplier ? ` ×${engines.lossless.multiplier}` : ""}` : null;
            const scaler = install ? badgeLabel(build, install.options?.model, install.build).full : engines?.mako?.spatial ? "Mako" : null;
            const active = scaler === "Mako" && frameGen?.startsWith("Mako") ? frameGen : [scaler, frameGen].filter(Boolean).join(" - ");
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
                        <span title={t(install.status === "active" ? "up.list.checked" : install.status === "broken" ? "up.list.review" : "up.list.unchecked")}
                          style={{ display: "flex", flexShrink: 0, color: statusColor(install.status) }}>
                          {install.status === "active" ? <LuCircleCheck size={14} /> : install.status === "broken" ? <LuTriangleAlert size={14} /> : <LuClock size={14} />}
                        </span>
                        <span style={{ color: theme.color.textPrimary }}>{active}</span>
                      </>
                    ) : active ? (
                      <span style={{ color: theme.color.textPrimary }}>{active}</span>
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
