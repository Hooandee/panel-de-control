import { FC } from "react";

import type { TdpOwnership } from "../api";
import { useI18n } from "../i18n";
import { ownershipView } from "../tdp/ownership";
import { theme } from "../theme";

export const TdpOwnershipStatus: FC<{ ownership: TdpOwnership }> = ({ ownership }) => {
  const { t } = useI18n();
  const view = ownershipView(ownership);
  if (!view.show) return null;
  const color = view.kind === "rejected" || view.kind === "conflict"
    ? theme.color.warn
    : theme.color.textMuted;
  return (
    <div style={{ fontSize: theme.font.caption, color }}>
      {t(`tdp.ownership.${view.kind}`, {
        requested: view.requested ?? "—",
        target: view.target ?? "—",
        applied: view.applied ?? "—",
      })}
    </div>
  );
};
