export interface PowerInput {
  inGame: boolean;
  screenOn: boolean;
  surfaceVisible: boolean;
  battery: { percent: number; charging: boolean } | null;
  threshold: number;
}

export type MotionState = "play" | "pause" | "freeze";

export function motionFor(input: PowerInput): MotionState {
  if (input.inGame || !input.screenOn || !input.surfaceVisible) return "pause";
  const { battery } = input;
  if (battery && !battery.charging && battery.percent < input.threshold) return "freeze";
  return "play";
}
