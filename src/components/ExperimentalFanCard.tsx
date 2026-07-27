import { FC } from "react";
import { PanelSectionRow, ToggleField, showModal } from "@decky/ui";
import { LuTriangleAlert } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

/**
 * Opt-in for experimental EC fan control on devices whose only channel is
 * unofficial (Legion Go S). Off = read-only monitor; enabling asks for an explicit
 * confirm first. When on, the curve editor (and its reset) render below — the
 * section handles that; this card just carries the toggle + the note.
 */
export const ExperimentalFanCard: FC<Props> = ({ enabled, onToggle }) => {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: theme.space.card }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          <LuTriangleAlert size={16} color={theme.color.warn} /> {t("fans.experimental.title")}
        </div>
        {!enabled && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.xs}px 0`, lineHeight: 1.4 }}>
            {t("fans.experimental.note")}
          </div>
        )}
        <ToggleField
          label={t("fans.experimental.toggle")}
          checked={enabled}
          bottomSeparator="none"
          onChange={(next: boolean) => {
            if (next)
              showModal(
                <ConfirmDialog
                  title={t("fans.experimental.confirm.title")}
                  desc={t("fans.experimental.confirm.desc")}
                  confirmLabel={t("fans.experimental.confirm.ok")}
                  cancelLabel={t("fans.experimental.confirm.cancel")}
                  icon={<LuTriangleAlert size={20} color={theme.color.warn} />}
                  onConfirm={() => onToggle(true)}
                />,
              );
            else onToggle(false);
          }}
        />
      </div>
    </PanelSectionRow>
  );
};
