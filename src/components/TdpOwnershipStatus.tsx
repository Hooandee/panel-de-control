import { FC } from "react";

import type { TdpOwnership } from "../api";
import { useI18n } from "../i18n";
import { ownershipMessage } from "../tdp/ownership";
import { theme } from "../theme";

export const TdpOwnershipStatus: FC<{
  ownership: TdpOwnership;
  onAc?: boolean;
  physicalMin?: number;
}> = ({ ownership, onAc, physicalMin }) => {
  const { t } = useI18n();
  const message = ownershipMessage(ownership, physicalMin, onAc);
  if (!message) return null;
  return (
    <div style={{ fontSize: theme.font.caption, color: message.warn ? theme.color.warn : theme.color.textMuted }}>
      {t(message.key, message.vars)}
    </div>
  );
};
