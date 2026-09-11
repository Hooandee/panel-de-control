export type LearningTag = "tdp" | "fans";
export type LearningState = "learning" | "paused" | "hidden";

export interface LearningInputs {
  inGame: boolean;
  telemetryOn: boolean;
  tdpSupported: boolean;
  fanSupported: boolean;
  scope: readonly LearningTag[];
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
  scope,
}: LearningInputs): LearningBadge {
  const tags: LearningTag[] = [];
  if (tdpSupported && scope.includes("tdp")) tags.push("tdp");
  if (fanSupported && scope.includes("fans")) tags.push("fans");

  if (!inGame || tags.length === 0) return { state: "hidden", tags: [] };

  return { state: telemetryOn ? "learning" : "paused", tags };
}
