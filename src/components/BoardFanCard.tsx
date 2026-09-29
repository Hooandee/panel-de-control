import { FC, useState } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { LuCpu } from "react-icons/lu";

import { BoardFanState, setBoardFanEnabled } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

export function boardFanNote(state: BoardFanState): string {
  if (!state.available?.length && !state.channels) return "fans.board.noDriver";
  if (state.enabled && state.channels) return "fans.board.active";
  if (state.last?.action === "load" && !state.last.ok) return "fans.board.noFans";
  if (state.channels && !state.enabled) return "fans.board.present";
  return "fans.board.note";
}

export const BoardFanCard: FC<{ state: BoardFanState; onChange: () => void }> = ({ state, onChange }) => {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const canToggle = !!state.available?.length || !!state.enabled;
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: theme.space.card }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          <LuCpu size={16} color={theme.color.accent} /> {t("fans.board.title")}
        </div>
        <div data-testid="board-fan-note" style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.xs}px 0`, lineHeight: 1.4 }}>
          {t(boardFanNote(state), { n: state.channels ?? 0 })}
        </div>
        {canToggle && (
          <ToggleField
            label={t("fans.board.toggle")}
            checked={!!state.enabled}
            disabled={busy}
            bottomSeparator="none"
            onChange={(next: boolean) => {
              setBusy(true);
              setBoardFanEnabled(next).catch(() => null).finally(() => {
                setBusy(false);
                onChange();
              });
            }}
          />
        )}
      </div>
    </PanelSectionRow>
  );
};
