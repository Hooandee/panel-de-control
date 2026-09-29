import { FC } from "react";

import type { TdpOwnership } from "../api";
import { useI18n } from "../i18n";
import { ownershipView } from "../tdp/ownership";
import { theme } from "../theme";

export const TdpOwnershipStatus: FC<{
  ownership: TdpOwnership;
  onAc?: boolean;
}> = ({ ownership, onAc }) => {
  const { t } = useI18n();
  const view = ownershipView(ownership);
  const overshoot = ownership.overshoot;
  const ownershipWins = view.show && view.kind !== "constrained" && view.kind !== "settling";
  if (overshoot && !ownershipWins) {
    const key = {
      correcting: "tdp.ownership.overshootCorrecting",
      restored: "tdp.ownership.overshootRestored",
      unresolved: "tdp.ownership.overshootUnresolved",
    }[overshoot.state];
    return (
      <div
        style={{
          fontSize: theme.font.caption,
          color: overshoot.state === "restored" ? theme.color.textMuted : theme.color.warn,
        }}
      >
        {t(key, { peak: Math.round(overshoot.peak_w), target: overshoot.target_w })}
      </div>
    );
  }
  if (!view.show) return null;
  const color = view.kind === "rejected" || view.kind === "conflict"
    ? theme.color.warn
    : theme.color.textMuted;
  const messageKey = view.kind === "constrained"
    && ownership.reason === "power_source_limit"
    && onAc
    ? "tdp.ownership.powerLimited"
    : `tdp.ownership.${view.kind}`;
  return (
    <div style={{ fontSize: theme.font.caption, color }}>
      {t(messageKey, {
        requested: view.requested ?? "—",
        target: view.target ?? "—",
        applied: view.applied ?? "—",
      })}
    </div>
  );
};
