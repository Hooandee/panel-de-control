import { LuCircleCheck, LuClock, LuSlidersHorizontal, LuTriangleAlert } from "react-icons/lu";
import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useState, type FC, type ComponentProps } from "react";

import { getUpscalersCompat, getUpscalersOverview, getUpscalersSelectorInstalls, type GameCompat } from "../api";
import { FocusableCard } from "../components/FocusableCard";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import { readUpscalersSelection } from "../launch/steamApi";
import { onUpscalersGameRequest, takePendingUpscalersGame } from "../upscalers/deepLink";
import { theme } from "../theme";
import { BulkPanel } from "../upscalers/BulkPanel";
import { GameView } from "../upscalers/GameView";
import { IN_GAME_MODES, publishOverview, readCoverBadges, readInGameMode, setUpscalersSectionOpen, writeCoverBadges, writeInGameMode, type InGameMode } from "../upscalers/overlays";
import { Fold, Label, SegmentRow } from "../upscalers/parts";
import { badgeLabel, fallbackLine } from "../upscalers/model";
import { MOTION_CSS, Skeleton, statusColor } from "../upscalers/parts";
import { publishSelectorContext } from "../upscalers/selectorContext";
import { steamLibraryFolders } from "../upscalers/steamLibraries";
import { showGame, takeHeldPage, type PageDraft } from "../upscalers/pageMemory";
import type { UpscalerChoice, UpscalersOverview } from "../upscalers/types";

const NO_COMPAT: Record<string, GameCompat> = {};

const NavigationGroup = Focusable as FC<ComponentProps<typeof Focusable> & { childFocusDisabled?: boolean }>;

export const EscaladoresSection: FC = () => {
  const { t } = useI18n();
  const [overview, setOverview] = useState<UpscalersOverview | null>(null);
  const [inventory, setInventory] = useState<{ appids: number[]; complete: boolean } | null>(null);
  const [failed, setFailed] = useState(false);
  const [held] = useState(takeHeldPage);
  const [selectedAppid, setSelectedAppid] = useState<number | null>(() => held?.appid ?? null);
  const [compatResult, setCompatResult] = useState<{ appids: string; partial: boolean; compat: Record<string, GameCompat> } | null>(null);
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
    let alive = true;
    getUpscalersSelectorInstalls(steamLibraryFolders())
      .then((result) => { if (alive) setInventory(result); })
      .catch(() => { if (alive) setInventory({ appids: [], complete: false }); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    setUpscalersSectionOpen(true);
    return () => setUpscalersSectionOpen(false);
  }, []);
  const closeGame = useCallback(() => {
    showGame(null);
    setSelectedAppid(null);
  }, []);

  const selection = useMemo(() => readUpscalersSelection(inventory?.appids ?? []), [overview, inventory]);
  const games = useMemo(() => {
    const installs = overview?.installs ?? {};
    return [...selection.games]
      .sort((a, b) => Number(String(b.liveAppid) in installs) - Number(String(a.liveAppid) in installs) || b.lastPlayed - a.lastPlayed);
  }, [overview, selection]);
  const selected = games.find((game) => game.liveAppid === selectedAppid);

  useEffect(() => {
    if (!overview) return;
    const open = () => {
      const hasGame = (appid: number) => games.some((game) => game.liveAppid === appid);
      const appid = takePendingUpscalersGame((id) => inventory !== null || hasGame(id));
      if (appid !== null && hasGame(appid)) setSelectedAppid(appid);
    };
    open();
    return onUpscalersGameRequest(open);
  }, [overview, games, inventory]);

  const appids = overview ? games.map((g) => String(g.liveAppid)).join(",") : "";
  const compatRead = compatResult?.appids === appids;
  const compat = compatResult?.compat ?? NO_COMPAT;
  const compatIds = useMemo(() => new Set(compatResult?.appids.split(",")), [compatResult]);
  useEffect(() => {
    if (!appids) return;
    let alive = true;
    const ids = appids.split(",");
    // The backend answers at most 400 games per call; a whole store library can be longer.
    const batches = Array.from({ length: Math.ceil(ids.length / 400) }, (_, index) => ids.slice(index * 400, index * 400 + 400));
    const libraries = steamLibraryFolders();
    Promise.all(batches.map((batch) => getUpscalersCompat(batch, libraries).catch(() => ({}))))
      .then((parts) => {
        if (!alive) return;
        const compat = Object.assign({}, ...parts);
        setCompatResult({ appids, partial: ids.some((id) => !compat[id]), compat });
      });
    return () => { alive = false; };
  }, [appids]);
  // Store shortcuts with no installed game behind them (Unifideck lists a whole library) have nothing to scale.
  // Shortcuts wait for that answer, so a library-only entry never shows up and then vanishes under the focus.
  const listed = useMemo(() => games.filter((game) => {
    const id = String(game.liveAppid);
    return compatIds.has(id) ? !compat[id]?.unavailable : !game.isNonSteam;
  }), [games, compat, compatIds]);

  useEffect(() => {
    if (failed) {
      publishSelectorContext(null);
      return;
    }
    if (!overview || selected) return;
    const listedIds = new Set(listed.map((game) => game.liveAppid));
    const priority = (sample: (typeof selection.steam)[number]) =>
      Number(!listedIds.has(sample.appid) || !sample.collection || sample.local !== "true");
    const samples = [...selection.steam]
      .sort((a, b) => priority(b) - priority(a))
      .slice(0, 12)
      .map((sample) => ({ ...sample,
        row: listedIds.has(sample.appid) ? "visible" as const : "unavailable" as const }));
    const shortcut_rows = listed.filter((game) => game.isNonSteam).length;
    const { no_metadata, not_game, unreadable } = selection;
    publishSelectorContext({
      observed_at: Math.floor(Date.now() / 1000),
      complete: inventory?.complete ?? null,
      compatibility: !appids ? "ready" : !compatRead ? "pending" : compatResult?.partial ? "partial" : "ready",
      recovered: selection.steam.filter((app) => app.manifest && (!app.collection || app.local !== "true")).length,
      steam_rows: listed.length - shortcut_rows,
      shortcut_rows,
      filtered: games.filter((game) => compat[String(game.liveAppid)]?.unavailable).length,
      no_metadata,
      not_game,
      unreadable,
      samples,
    });
  }, [overview, failed, selected, games, listed, appids, compatRead, compatResult, compat, selection, inventory]);

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
            const makoName = engines?.mako?.engine === 5 ? "Mako 5" : "Mako 4";
            const frameGen = engines?.mako?.fg ? `${makoName}${engines.mako.multiplier ? ` ×${engines.mako.multiplier}` : ""}`
              : engines?.lossless ? `Lossless${engines.lossless.multiplier ? ` ×${engines.lossless.multiplier}` : ""}` : null;
            const fallback = install?.fallback ?? null;
            const scaler = install ? (fallback ? (fallback.observed ?? t("up.fallback.coverNone", { from: fallback.requested })) : badgeLabel(build, install.options?.model, install.build).full) : engines?.mako?.spatial ? makoName : null;
            const active = scaler === makoName && frameGen?.startsWith(makoName) ? frameGen : [scaler, frameGen].filter(Boolean).join(" - ");
            return (
              <FocusableCard key={game.instanceKey} onActivate={() => setSelectedAppid(game.liveAppid)}>
                <GameCover urls={game.coverUrls} name={game.name} width={30} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {game.name}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, marginTop: 2, minHeight: 16 }}>
                    {install ? (
                      <>
                        <span title={fallback ? fallbackLine(fallback, t) : t(install.status === "active" ? "up.list.checked" : install.status === "broken" ? "up.list.review" : "up.list.unchecked")}
                          style={{ display: "flex", flexShrink: 0, color: statusColor(fallback ? "loaded" : install.status) }}>
                          {fallback ? <LuTriangleAlert size={14} /> : install.status === "active" ? <LuCircleCheck size={14} /> : install.status === "broken" ? <LuTriangleAlert size={14} /> : <LuClock size={14} />}
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
