import { FC } from "react";
import { LuTriangleAlert } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

/**
 * Warns when Handheld Daemon's TDP plugin (which also drives its fan curve) is
 * enabled at the same time as our power control — both write the same firmware
 * rails and fight (last-writer-wins → jitter). We only WARN and guide; we never
 * touch HHD's settings (the user's boundary). Rendered only when a real conflict
 * is detected. Shown in Ajustes.
 */
export const ControllerConflictCard: FC = () => {
  const { t } = useI18n();
  return (
    <div
      style={{
        ...theme.card,
        padding: theme.space.md,
        overflow: "hidden",
        boxShadow: `inset 0 0 0 1px ${theme.color.warn}55`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: theme.space.xs,
          fontSize: theme.font.body,
          fontWeight: 700,
          color: theme.color.warn,
        }}
      >
        <LuTriangleAlert size={16} color={theme.color.warn} /> {t("mandos.conflict.title")}
      </div>
      <div
        style={{
          fontSize: theme.font.caption,
          color: theme.color.textMuted,
          marginTop: theme.space.xs,
          lineHeight: 1.4,
        }}
      >
        {t("mandos.conflict.desc")}
      </div>
    </div>
  );
};
