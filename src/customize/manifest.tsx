import { ReactNode } from "react";
import {
  LuGauge, LuSlidersHorizontal, LuFan, LuSettings,
  LuLeaf, LuBatteryCharging, LuBatteryFull, LuCpu, LuSun, LuVolume2, LuWind, LuThermometer, LuChartSpline,
  LuLightbulb, LuPalette, LuGamepad2, LuMemoryStick, LuActivity, LuHeartPulse, LuAudioLines,
  LuSparkles, LuMoon, LuReplace, LuSlidersVertical, LuRocket, LuLayoutDashboard, LuPaintbrush, LuPuzzle, LuHardDrive,
} from "react-icons/lu";
import type { SectionIcon } from "../sections/types";
import type { LearningTag } from "../learning/logic";
import type { ModuleId } from "./moduleLogic";

export interface ItemMeta {
  id: string;
  labelKey: string;
  icon: ReactNode;
}
export interface TabMeta {
  id: string;
  labelKey: string;
  descriptionKey: string;
  accent: string;
  icon: SectionIcon;
  learningTags?: readonly LearningTag[];
}
export interface BlockDef extends ItemMeta {
  desktopOnly?: boolean;
  handheldOnly?: boolean;
}
export interface SubitemMeta extends ItemMeta {
  moduleId?: ModuleId;
  capability?: "chargeLimit";
}

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
export const TABS: TabMeta[] = [
  { id: "power", labelKey: "nav.power", descriptionKey: "nav.power.desc", accent: "#287d8c", icon: (size) => <LuGauge size={size} />, learningTags: ["tdp"] },
  { id: "system", labelKey: "nav.system", descriptionKey: "nav.system.desc", accent: "#647084", icon: (size) => <LuSlidersHorizontal size={size} /> },
  { id: "display", labelKey: "nav.display", descriptionKey: "nav.display.desc", accent: "#a05f79", icon: (size) => <LuPalette size={size} /> },
  { id: "fans", labelKey: "nav.fans", descriptionKey: "nav.fans.desc", accent: "#39796e", icon: (size) => <LuFan size={size} />, learningTags: ["fans"] },
  { id: "audio", labelKey: "nav.audio", descriptionKey: "nav.audio.desc", accent: "#96713e", icon: (size) => <LuAudioLines size={size} /> },
  { id: "mandos", labelKey: "nav.mandos", descriptionKey: "nav.mandos.desc", accent: "#64609b", icon: (size) => <LuGamepad2 size={size} /> },
  { id: "hud", labelKey: "nav.hud", descriptionKey: "nav.hud.desc", accent: "#3e7e5e", icon: (size) => <LuLayoutDashboard size={size} /> },
  { id: "params", labelKey: "nav.params", descriptionKey: "nav.params.desc", accent: "#955e44", icon: (size) => <LuRocket size={size} /> },
  { id: "cleaner", labelKey: "nav.cleaner", descriptionKey: "nav.cleaner.desc", accent: "#507e86", icon: (size) => <LuHardDrive size={size} /> },
  { id: "themes", labelKey: "nav.themes", descriptionKey: "nav.themes.desc", accent: "#925783", icon: (size) => <LuPaintbrush size={size} /> },
  { id: "settings", labelKey: "nav.settings", descriptionKey: "nav.settings.desc", accent: "#626b73", icon: (size) => <LuSettings size={size} /> },
];

export const CATEGORY_IDS = TABS.map((t) => t.id).filter((id) => id !== PINNED_TAB);

export const SECTION_BLOCKS: Record<string, BlockDef[]> = {
  power: [
    { id: "desktopPower", labelKey: "desktop.power.title", icon: <LuGauge size={ICON} />, desktopOnly: true },
    { id: "autoTdp", labelKey: "tdp.auto.title", icon: <LuActivity size={ICON} />, handheldOnly: true },
  ],
  system: [
    { id: "eco", labelKey: "system.eco.title", icon: <LuLeaf size={ICON} /> },
    { id: "battery", labelKey: "system.battery.title", icon: <LuBatteryFull size={ICON} /> },
    { id: "cpu", labelKey: "system.cpu.title", icon: <LuCpu size={ICON} /> },
    { id: "gpu", labelKey: "gpu.clock.title", icon: <LuMemoryStick size={ICON} /> },
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
    { id: "magicModules", labelKey: "mandos.modules.title", icon: <LuPuzzle size={ICON} /> },
  ],
};

export function blocksForSection(sectionId: string, desktopMode = false): BlockDef[] {
  return (SECTION_BLOCKS[sectionId] ?? []).filter((block) =>
    (!block.desktopOnly || desktopMode) && (!block.handheldOnly || !desktopMode));
}

export function customizationBlocks(
  sectionId: string,
  desktopMode: boolean,
  presentIds: string[] | null,
): BlockDef[] {
  const blocks = blocksForSection(sectionId, desktopMode);
  if (!presentIds) return blocks;
  return blocks.filter((block) => block.desktopOnly || presentIds.includes(block.id));
}

/**
 * Fixed sub-items WITHIN a block that the user can HIDE (only hide — they're a
 * fixed part of their block, not reorderable). Keyed by block id. Section render
 * code drops them with subitemHidden(layout.subitems, <block>, <sub-item id>).
 */
export const SUBITEMS: Record<string, SubitemMeta[]> = {
  battery: [
    { id: "health", labelKey: "system.battery.healthGroup", icon: <LuHeartPulse size={ICON} /> },
    {
      id: "limit",
      labelKey: "system.battery.limit",
      icon: <LuBatteryCharging size={ICON} />,
      moduleId: "chargeLimit",
      capability: "chargeLimit",
    },
  ],
};

export function subitemsFor(blockId: string, chargeLimitSupported: boolean): SubitemMeta[] {
  return (SUBITEMS[blockId] ?? []).filter(
    (item) => item.capability !== "chargeLimit" || chargeLimitSupported,
  );
}

/** Default block-id order for a section (empty for sections without blocks). */
export function blockOrder(sectionId: string, desktopMode = false): string[] {
  return blocksForSection(sectionId, desktopMode).map((b) => b.id);
}

/**
 * Blocks a custom view can pick, per section. Superset of SECTION_BLOCKS: adds the
 * fixed cores that aren't reorderable in their own tab but CAN be placed in a view
 * (Potencia's TDP arc). Used only by the custom-view editor's block picker.
 */
export const PICKABLE_BLOCKS: Record<string, BlockDef[]> = {
  ...SECTION_BLOCKS,
  power: [
    { id: "tdp", labelKey: "customize.block.tdp", icon: <LuGauge size={ICON} />, handheldOnly: true },
    ...SECTION_BLOCKS.power,
  ],
};

export function blockAvailableInMode(id: string, desktopMode: boolean): boolean {
  for (const blocks of Object.values(PICKABLE_BLOCKS)) {
    const block = blocks.find((candidate) => candidate.id === id);
    if (!block) continue;
    return (!block.desktopOnly || desktopMode) && (!block.handheldOnly || !desktopMode);
  }
  return true;
}

export function pickableBlocksForSection(
  sectionId: string,
  desktopMode: boolean,
  presentIds: string[] | null,
): BlockDef[] {
  if (sectionId === "power" && !desktopMode) {
    const tdp = PICKABLE_BLOCKS.power.find((block) => block.id === "tdp")!;
    return [tdp, ...customizationBlocks(sectionId, false, presentIds)];
  }
  return customizationBlocks(sectionId, desktopMode, presentIds);
}
