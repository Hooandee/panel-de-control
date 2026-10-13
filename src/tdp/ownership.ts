import type { TdpOwnership } from "../api";

export interface OwnershipView {
  show: boolean;
  kind: "constrained" | "settling" | "rejected" | "unverifiable" | "conflict";
  requested: number | null;
  target: number | null;
  applied: number | null;
  persistent: boolean;
  boostFloor: { pl2: number; pl3: number } | null;
}

export function ownershipView(ownership: TdpOwnership, physicalMin?: number): OwnershipView {
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
  const secondaryMinimumConfirmed = (["pl2", "pl3"] as const).every((rail) => {
    const railTarget = ownership.target[rail];
    if (typeof railTarget !== "number") return true;
    const railRequested = ownership.requested[rail];
    const railApplied = ownership.applied[rail];
    return typeof railRequested === "number"
      && railTarget >= railRequested
      && railApplied === railTarget;
  });
  const onlyRaisedSecondary = secondaryChanges.some((change) => change > 0)
    && secondaryChanges.every((change) => change >= 0);
  const secondaryOnlyConstraint = ownership.status === "constrained"
    && ownership.reason === "safe_min"
    && requested !== null
    && requested === target
    && target === applied
    && onlyRaisedSecondary
    && secondaryMinimumConfirmed;
  const confirmedMinimumConstraint = ownership.status === "constrained"
    && ["safe_min", "live_min"].includes(ownership.reason)
    && requested !== null
    && target !== null
    && physicalMin !== undefined
    && requested < physicalMin
    && target === physicalMin
    && target === applied
    && secondaryMinimumConfirmed;
  const { pl2: boostPl2, pl3: boostPl3 } = ownership.target;
  const boostFloor = (secondaryOnlyConstraint || confirmedMinimumConstraint)
    && onlyRaisedSecondary
    && typeof boostPl2 === "number"
    && typeof boostPl3 === "number"
    ? { pl2: boostPl2, pl3: boostPl3 }
    : null;
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
        && !confirmedMinimumConstraint
        && !["in_sync", "unsupported"].includes(ownership.status)
      )
    ),
    kind,
    requested,
    target,
    applied,
    persistent,
    boostFloor,
  };
}

export interface OwnershipMessage {
  key: string;
  vars: Record<string, number>;
  warn: boolean;
}

// Only what the user needs to know, attributed to the device: it refuses, caps or ignores
// the limit, or something else keeps changing it. States that work, settle or are
// corrected automatically stay in the logs.
export function ownershipMessage(
  ownership: TdpOwnership,
  physicalMin?: number,
  onAc?: boolean,
): OwnershipMessage | null {
  if (["control_disabled", "firmware_mode"].includes(ownership.reason)) return null;
  const view = ownershipView(ownership, physicalMin);
  if (ownership.status === "rejected") {
    if (view.target === null) return { key: "tdp.ownership.rejectedUnknown", vars: {}, warn: true };
    return view.applied !== null
      ? { key: "tdp.ownership.rejected", vars: { target: view.target, applied: view.applied }, warn: true }
      : { key: "tdp.ownership.rejectedNoValue", vars: { target: view.target }, warn: true };
  }
  if (ownership.overshoot?.state === "unresolved") {
    return { key: "tdp.ownership.overshootUnresolved", vars: { target: ownership.overshoot.target_w }, warn: true };
  }
  if (ownership.conflict_persistent) return { key: "tdp.ownership.conflict", vars: {}, warn: true };
  if (view.show && ownership.status === "constrained" && view.applied !== null) {
    const key = ["safe_min", "live_min"].includes(ownership.reason)
      ? "tdp.ownership.minimum"
      : ownership.reason === "power_source_limit" && onAc
        ? "tdp.ownership.powerLimited"
        : "tdp.ownership.constrained";
    return { key, vars: { applied: view.applied }, warn: false };
  }
  return null;
}
