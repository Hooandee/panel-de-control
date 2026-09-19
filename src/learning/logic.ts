export type LearningTag = "tdp" | "fans";
export type LearningState = "learning" | "paused" | "hidden";

export interface LearningInputs {
  inGame: boolean;
  telemetryOn: boolean;
  tdpSupported: boolean;
  fanSupported: boolean;
  autoTdpActive?: boolean;
  scope?: readonly LearningTag[];
}

export interface LearningBadge {
  state: LearningState;
  tags: LearningTag[];
}

export function learningBadge({
  inGame,
  telemetryOn,
  tdpSupported,
  fanSupported,
  autoTdpActive = false,
  scope = ["tdp", "fans"],
}: LearningInputs): LearningBadge {
  const tags: LearningTag[] = [];
  if (tdpSupported && !autoTdpActive && scope.includes("tdp")) tags.push("tdp");
  if (fanSupported && scope.includes("fans")) tags.push("fans");

  if (!inGame || tags.length === 0) return { state: "hidden", tags: [] };

  return { state: telemetryOn ? "learning" : "paused", tags };
}
