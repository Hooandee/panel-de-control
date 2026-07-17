import { FC, useMemo, useState } from "react";
import { PanelSectionRow, TextField } from "@decky/ui";
import { LuChevronRight, LuPlay, LuInfo, LuSearch, LuArrowDownUp, LuSlidersHorizontal, LuEyeOff } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "../components/Loading";
import { GameCover } from "../components/GameCover";
import { FocusableCard } from "../components/FocusableCard";
import { useGames, GameListItem } from "../launch/useGames";
import { useRunningGame } from "../tdp/useRunningGame";
import { useHiddenGames } from "../launch/useHiddenGames";
import { sortGames, SortMode } from "../launch/sort";
import { openLaunchEditorModal } from "../components/LaunchEditorModal";
import { openCustomVarsManager } from "../components/CustomVarsManager";

const SORT_MODES: SortMode[] = ["recent", "alpha", "played"];

const GameRow: FC<{ game: GameListItem; hidden: boolean; onClosed: () => void }> = ({ game, hidden, onClosed }) => {
  const { t } = useI18n();
  return (
    <FocusableCard onActivate={() => openLaunchEditorModal(game, onClosed)} style={{ opacity: hidden ? 0.55 : 1 }}>
      <GameCover url={game.coverUrl} name={game.name} width={40} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {game.name}
        </div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {game.isNonSteam ? t("params.badge.nonSteam") : t("params.badge.steam")}
        </div>
      </div>
      {game.activeCount > 0 && (
        <span style={{ fontSize: 10, color: theme.color.onAccent, background: theme.color.accent, borderRadius: 20, padding: "2px 8px", flexShrink: 0 }}>
          {t("params.activeCount", { n: game.activeCount })}
        </span>
      )}
      <LuChevronRight size={16} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
    </FocusableCard>
  );
};

/** Shortcut to the currently-running game's editor. Launch options are read at
 *  launch, so edits need a game restart (shown on the card). */
const RunningNowCard: FC<{ games: GameListItem[]; onClosed: () => void }> = ({ games, onClosed }) => {
  const { t } = useI18n();
  const running = useRunningGame();
  // running.appid is the STABLE key (stableGameKey) — join on that, not liveAppid.
  const game = running ? games.find((g) => g.stableKey === running.appid) : undefined;
  if (!game) return null;
  return (
    <FocusableCard emphasized onActivate={() => openLaunchEditorModal(game, onClosed)}>
      <GameCover url={game.coverUrl} name={game.name} width={44} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: theme.font.caption, color: theme.color.accent, display: "flex", alignItems: "center", gap: 4 }}>
          <LuPlay size={11} /> {t("params.running.now")}
        </div>
        <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {game.name}
        </div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, display: "flex", alignItems: "center", gap: 4 }}>
          <LuInfo size={10} style={{ flexShrink: 0 }} /> {t("params.running.restart")}
        </div>
      </div>
      <LuChevronRight size={16} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
    </FocusableCard>
  );
};

/** Launch-options manager: list installed games (Steam + non-Steam); tap one to
 *  edit its launch parameters full-screen. Sorted by recent play by default. */
export const ParametrosSection: FC = () => {
  const { t } = useI18n();
  const { games, reload } = useGames();
  const { hidden } = useHiddenGames();
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [sort, setSort] = useState<SortMode>("recent");

  const shown = useMemo(() => {
    if (!games) return null;
    const needle = query.trim().toLowerCase();
    let f = games.filter((g) => hidden.has(g.stableKey) === showHidden);
    if (needle) f = f.filter((g) => g.name.toLowerCase().includes(needle));
    return sortGames(f, sort);
  }, [games, query, sort, hidden, showHidden]);
  const hiddenCount = useMemo(() => (games ? games.filter((g) => hidden.has(g.stableKey)).length : 0), [games, hidden]);

  if (games === null) return <Loading />;

  const cycleSort = () => setSort(SORT_MODES[(SORT_MODES.indexOf(sort) + 1) % SORT_MODES.length]);
  const toggleSearch = () =>
    setSearchOpen((o) => {
      if (o) setQuery("");
      return !o;
    });

  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <RunningNowCard games={games} onClosed={reload} />

        <div style={{ display: "flex", gap: theme.space.sm }}>
          <FocusableCard onActivate={cycleSort} style={{ flex: 1, gap: 8, padding: "7px 12px" }}>
            <LuArrowDownUp size={14} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>
              {t(`params.sort.${sort}`)}
            </span>
          </FocusableCard>
          <FocusableCard onActivate={toggleSearch} style={{ flexShrink: 0, padding: "7px 12px" }}>
            <LuSearch size={16} color={searchOpen ? theme.color.accent : theme.color.textMuted} />
          </FocusableCard>
          {(hiddenCount > 0 || showHidden) && (
            <FocusableCard onActivate={() => setShowHidden((v) => !v)} style={{ flexShrink: 0, padding: "7px 12px", gap: 6 }}>
              <LuEyeOff size={16} color={showHidden ? theme.color.accent : theme.color.textMuted} />
              {hiddenCount > 0 && (
                <span style={{ fontSize: theme.font.caption, color: showHidden ? theme.color.accent : theme.color.textMuted }}>{hiddenCount}</span>
              )}
            </FocusableCard>
          )}
        </div>

        {searchOpen && (
          <TextField
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            // @ts-expect-error Decky TextField forwards input attrs; placeholder is valid.
            placeholder={t("params.search")}
          />
        )}

        <FocusableCard onActivate={() => openCustomVarsManager(reload)}>
          <LuSlidersHorizontal size={16} color={theme.color.accent} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("customVars.title")}</span>
          <LuChevronRight size={16} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
        </FocusableCard>

        {games.length === 0 ? (
          <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, padding: theme.space.sm }}>{t("params.empty")}</div>
        ) : shown!.length === 0 ? (
          <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, padding: theme.space.sm }}>
            {t(showHidden && !query.trim() ? "params.hiddenEmpty" : "params.noMatch")}
          </div>
        ) : (
          shown!.map((g) => (
            <GameRow key={g.stableKey} game={g} hidden={showHidden} onClosed={reload} />
          ))
        )}
      </div>
    </PanelSectionRow>
  );
};
