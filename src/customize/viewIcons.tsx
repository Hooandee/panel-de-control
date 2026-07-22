import { ReactNode } from "react";
import {
  LuStar, LuZap, LuGamepad2, LuThermometer, LuGauge, LuLayoutGrid,
  LuMonitor, LuCpu, LuSlidersHorizontal, LuSparkles,
} from "react-icons/lu";

import { ViewIconKey } from "./views";

/** The curated tab-icon set for custom views (key → node). Used by the shell's
 *  tab bar and the editor's icon picker. */
export function viewIconNode(key: ViewIconKey, size = 15): ReactNode {
  const Icon = ICONS[key] ?? LuStar;
  return <Icon size={size} />;
}

const ICONS: Record<ViewIconKey, typeof LuStar> = {
  star: LuStar,
  zap: LuZap,
  gamepad: LuGamepad2,
  thermometer: LuThermometer,
  gauge: LuGauge,
  grid: LuLayoutGrid,
  monitor: LuMonitor,
  cpu: LuCpu,
  sliders: LuSlidersHorizontal,
  sparkles: LuSparkles,
};
