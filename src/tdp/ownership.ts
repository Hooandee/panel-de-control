import type { TdpOwnership } from "../api";

export interface OwnershipView {
  show: boolean;
  kind: "constrained" | "settling" | "rejected" | "unverifiable" | "conflict";
  requested: number | null;
  target: number | null;
  applied: number | null;
  persistent: boolean;
}

export function ownershipView(ownership: TdpOwnership): OwnershipView {
  const persistent = ownership.conflict_persistent;
  const inactive = ["control_disabled", "firmware_mode"].includes(ownership.reason);
  const requested = ownership.requested.pl1 ?? null;
  const target = ownership.target.pl1 ?? null;
  const applied = ownership.applied.pl1 ?? null;
  const secondaryChanges = (["pl2", "pl3"] as const).flatMap((rail) => {
    const railRequested = ownership.requested[rail];
    const railTarget = ownership.target[rail];
    return typeof railRequested === "number" && typeof railTarget === "number"
      ? [railTarget - railRequested]
      : [];
  });
  const onlyRaisedSecondary = secondaryChanges.some((change) => change > 0)
    && secondaryChanges.every((change) => change >= 0);
  const secondaryOnlyConstraint = ownership.status === "constrained"
    && ownership.reason === "safe_min"
    && requested !== null
    && requested === target
    && target === applied
    && onlyRaisedSecondary;
  let kind: OwnershipView["kind"];
  if (persistent) {
    kind = "conflict";
  } else if (ownership.status === "constrained") {
    kind = "constrained";
  } else if (ownership.status === "rejected") {
    kind = "rejected";
  } else if (ownership.status === "unverifiable") {
    kind = "unverifiable";
  } else {
    kind = "settling";
  }
  return {
    show: !inactive && (
      persistent || (
        !secondaryOnlyConstraint
        && !["in_sync", "unsupported"].includes(ownership.status)
      )
    ),
    kind,
    requested,
    target,
    applied,
    persistent,
  };
}
