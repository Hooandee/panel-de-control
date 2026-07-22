import { ReactNode } from "react";
import {
  LuGauge, LuSlidersHorizontal, LuFan, LuSettings,
  LuLeaf, LuBatteryFull, LuCpu, LuSun, LuVolume2, LuWind, LuThermometer, LuChartSpline,
  LuLightbulb, LuPalette, LuGamepad2, LuMemoryStick, LuActivity, LuHeartPulse,
  LuSparkles, LuMoon, LuReplace, LuSlidersVertical, LuRocket,
} from "react-icons/lu";

/** Presentation metadata shared by a tab and a configurable block. */
export interface ItemMeta {
  id: string;
  labelKey: string;
  icon: ReactNode;
}
export type BlockDef = ItemMeta;

/** The tab that can never be hidden — the escape hatch back to the customization
 *  editor. Single source of truth for both the shell and the editor. */
export const PINNED_TAB = "settings";

/** Potencia is never auto-hidden: its master switch being off drops it to a
 *  monitor-only view, not gone. Still hidable explicitly from the editor. */
export const POWER_TAB = "power";

const ICON = 15;

/**
 * The tabs (id + label + icon), in DEFAULT order. Kept here — decoupled from the
 * section Components in registry.tsx — so both the registry AND the customization
 * editor read the same tab metadata without a circular import.
 */
export const TABS: ItemMeta[] = [
  { id: "power", labelKey: "nav.power", icon: <LuGauge size={ICON} /> },
  { id: "system", labelKey: "nav.system", icon: <LuSlidersHorizontal size={ICON} /> },
  { id: "display", labelKey: "nav.display", icon: <LuPalette size={ICON} /> },
  { id: "fans", labelKey: "nav.fans", icon: <LuFan size={ICON} /> },
  { id: "mandos", labelKey: "nav.mandos", icon: <LuGamepad2 size={ICON} /> },
  { id: "params", labelKey: "nav.params", icon: <LuRocket size={ICON} /> },
  { id: "settings", labelKey: "nav.settings", icon: <LuSettings size={ICON} /> },
];

/** Category (section) ids the editor lists: the tabs minus the pinned Settings. */
export const CATEGORY_IDS = TABS.map((t) => t.id).filter((id) => id !== PINNED_TAB);

/**
 * The configurable blocks per section, in DEFAULT order. Single source of truth
 * for BOTH the customization editor (labels/icons) and each section's default
 * block order. Potencia's core (arc + slider + presets) is a fixed conditional
 * flow, but its two extras — the GPU-clock card and the Auto‑TDP toggle — are
 * reorderable/hideable blocks (GPU first by default).
 *
 * Section render code must key its block nodes by exactly these ids.
 */
export const SECTION_BLOCKS: Record<string, BlockDef[]> = {
  power: [
    { id: "gpu", labelKey: "gpu.clock.title", icon: <LuMemoryStick size={ICON} /> },
    { id: "autoTdp", labelKey: "tdp.auto.title", icon: <LuActivity size={ICON} /> },
  ],
  system: [
    { id: "eco", labelKey: "system.eco.title", icon: <LuLeaf size={ICON} /> },
    { id: "battery", labelKey: "system.battery.title", icon: <LuBatteryFull size={ICON} /> },
    { id: "cpu", labelKey: "system.cpu.title", icon: <LuCpu size={ICON} /> },
    { id: "brightness", labelKey: "system.brightness", icon: <LuSun size={ICON} /> },
    { id: "volume", labelKey: "system.volume", icon: <LuVolume2 size={ICON} /> },
    { id: "colores", labelKey: "system.rgb.title", icon: <LuLightbulb size={ICON} /> },
  ],
  fans: [
    { id: "fanRpm", labelKey: "customize.block.fanRpm", icon: <LuWind size={ICON} /> },
    { id: "temps", labelKey: "customize.block.temps", icon: <LuThermometer size={ICON} /> },
    { id: "curve", labelKey: "fans.curve.title", icon: <LuChartSpline size={ICON} /> },
  ],
  display: [
    { id: "oled", labelKey: "display.oled.title", icon: <LuSparkles size={ICON} /> },
    { id: "color", labelKey: "customize.block.color", icon: <LuPalette size={ICON} /> },
    { id: "hdr", labelKey: "display.hdr", icon: <LuSun size={ICON} /> },
    { id: "night", labelKey: "display.night", icon: <LuMoon size={ICON} /> },
  ],
  mandos: [
    { id: "manager", labelKey: "customize.block.manager", icon: <LuGamepad2 size={ICON} /> },
    { id: "remap", labelKey: "mandos.remap.title", icon: <LuReplace size={ICON} /> },
    { id: "settings", labelKey: "mandos.settings.title", icon: <LuSlidersVertical size={ICON} /> },
  ],
};

/**
 * Fixed sub-items WITHIN a block that the user can HIDE (only hide — they're a
 * fixed part of their block, not reorderable). Keyed by block id. Section render
 * code drops them with subitemHidden(layout.subitems, <block>, <sub-item id>).
 */
export const SUBITEMS: Record<string, ItemMeta[]> = {
  battery: [
    { id: "health", labelKey: "system.battery.healthGroup", icon: <LuHeartPulse size={ICON} /> },
  ],
};

/** Default block-id order for a section (empty for sections without blocks). */
export function blockOrder(sectionId: string): string[] {
  return (SECTION_BLOCKS[sectionId] ?? []).map((b) => b.id);
}

/**
 * Blocks a custom view can pick, per section. Superset of SECTION_BLOCKS: adds the
 * fixed cores that aren't reorderable in their own tab but CAN be placed in a view
 * (Potencia's TDP arc). Used only by the custom-view editor's block picker.
 */
export const PICKABLE_BLOCKS: Record<string, BlockDef[]> = {
  ...SECTION_BLOCKS,
  power: [
    { id: "tdp", labelKey: "customize.block.tdp", icon: <LuGauge size={ICON} /> },
    ...SECTION_BLOCKS.power,
  ],
};
