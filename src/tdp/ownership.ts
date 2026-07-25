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
      persistent || !["in_sync", "unsupported"].includes(ownership.status)
    ),
    kind,
    requested: ownership.requested.pl1 ?? null,
    target: ownership.target.pl1 ?? null,
    applied: ownership.applied.pl1 ?? null,
    persistent,
  };
}
