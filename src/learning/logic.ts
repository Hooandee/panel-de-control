// Pure decision logic for the persistent "learning" banner shown under the
// DeviceHeader. Decides — by DEVICE CAPABILITY — whether we are learning, paused,
// or should say nothing at all. Telemetry is one stream that feeds both TDP and
// fan learning; the tags reflect only what THIS device can actually learn/apply
// (no tag for a subsystem this machine can't control).

export type LearningTag = "tdp" | "fans";
export type LearningState = "learning" | "paused" | "hidden";

export interface LearningInputs {
  /** A game is in the foreground (we only learn in-game). */
  inGame: boolean;
  /** Telemetry opt-in is on. */
  telemetryOn: boolean;
  /** A real TDP write backend exists on this device. */
  tdpSupported: boolean;
  /** This device can WRITE fan curves (Null backend → false). */
  fanSupported: boolean;
}

export interface LearningBadge {
  state: LearningState;
  /** Which subsystems this device can learn — drives the [TDP][Ventiladores] chips. */
  tags: LearningTag[];
}

/**
 * - No game, or nothing this device can learn → hidden.
 * - In-game + a learnable subsystem, telemetry off → paused (with tags, so the
 *   copy can name what's paused).
 * - In-game + a learnable subsystem + telemetry on → learning.
 */
export function learningBadge({
  inGame,
  telemetryOn,
  tdpSupported,
  fanSupported,
}: LearningInputs): LearningBadge {
  const tags: LearningTag[] = [];
  if (tdpSupported) tags.push("tdp");
  if (fanSupported) tags.push("fans");

  // Only learns in-game; only if there's something learnable at all.
  if (!inGame || tags.length === 0) return { state: "hidden", tags: [] };

  return { state: telemetryOn ? "learning" : "paused", tags };
}
