import { ComponentType } from "react";
import { LuMoon, LuLeaf, LuGauge, LuFlame, LuRocket } from "react-icons/lu";

export const ZONE_ICON: Record<string, ComponentType<{ size?: number; color?: string }>> = {
  save: LuMoon,
  eco: LuLeaf,
  balanced: LuGauge,
  hot: LuFlame,
  turbo: LuRocket,
};
