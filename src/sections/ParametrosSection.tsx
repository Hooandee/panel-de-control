import { FC, useMemo, useState } from "react";
import { PanelSectionRow, TextField, Focusable } from "@decky/ui";
import { LuChevronRight, LuGamepad2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "../components/Loading";
import { useGames, GameListItem } from "../launch/useGames";
import { openLaunchEditorModal } from "../components/LaunchEditorModal";

const GameRow: FC<{ game: GameListItem; onClosed: () => void }> = ({ game, onClosed }) => {
  const { t } = useI18n();
  return (
    <Focusable
      style={{
        display: "flex", alignItems: "center", gap: theme.space.md,
        ...theme.card, padding: `${theme.space.sm}px ${theme.space.md}px`, cursor: "pointer",
      }}
      onActivate={() => openLaunchEditorModal(game, onClosed)}
      onClick={() => openLaunchEditorModal(game, onClosed)}
    >
      <LuGamepad2 size={18} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
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
    </Focusable>
  );
};

/** Launch-options manager: list installed games (Steam + non-Steam); tap one to
 *  edit its launch parameters full-screen. */
export const ParametrosSection: FC = () => {
  const { t } = useI18n();
  const { games, reload } = useGames();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!games) return null;
    const needle = query.trim().toLowerCase();
    return needle ? games.filter((g) => g.name.toLowerCase().includes(needle)) : games;
  }, [games, query]);

  if (games === null) return <Loading />;

  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <TextField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          // @ts-expect-error Decky TextField forwards input attrs; placeholder is valid.
          placeholder={t("params.search")}
        />
        {games.length === 0 ? (
          <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, padding: theme.space.sm }}>{t("params.empty")}</div>
        ) : filtered!.length === 0 ? (
          <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, padding: theme.space.sm }}>{t("params.noMatch")}</div>
        ) : (
          filtered!.map((g) => <GameRow key={g.stableKey} game={g} onClosed={reload} />)
        )}
      </div>
    </PanelSectionRow>
  );
};
