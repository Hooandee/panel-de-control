import { ReactNode } from "react";
import {
  LuLeaf, LuGauge, LuRocket, LuZap, LuBatteryLow, LuFlame, LuSnowflake,
  LuMoon, LuSun, LuPlane, LuMonitor, LuGamepad2,
} from "react-icons/lu";

// Icon ids stored in a preset. Keep ids stable (persisted).
export const PRESET_ICON_KEYS = [
  "bolt", "battery", "flame", "snow", "moon", "sun", "plane", "monitor",
  "gamepad", "leaf", "gauge", "rocket",
] as const;
export type PresetIconKey = (typeof PRESET_ICON_KEYS)[number];

const MAP: Record<string, (p: { size?: number }) => ReactNode> = {
  bolt: LuZap, battery: LuBatteryLow, flame: LuFlame, snow: LuSnowflake,
  moon: LuMoon, sun: LuSun, plane: LuPlane, monitor: LuMonitor,
  gamepad: LuGamepad2, leaf: LuLeaf, gauge: LuGauge, rocket: LuRocket,
};

export function presetIconNode(key: string, size = 16): ReactNode {
  const Icon = MAP[key] ?? LuZap;
  return <Icon size={size} />;
}
