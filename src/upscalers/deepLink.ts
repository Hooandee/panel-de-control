import { Navigation, QuickAccessTab } from "@decky/ui";

import { setActivePlugin } from "../deckyInternal";
import { PLUGIN_IDENTITY_NAME } from "../pluginListName";
import { writeActiveTab } from "../sections/activeTab";
import { setShellMode } from "../sections/shellMode";

const SECTION_ID = "upscalers";
const listeners = new Set<() => void>();
let pending: number | null = null;

/** The game the next Escaladores mount should open, consumed once. */
export function takePendingUpscalersGame(): number | null {
  const appid = pending;
  pending = null;
  return appid;
}

export function onUpscalersGameRequest(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Opens Panel's Quick Access panel straight on this game's Escaladores page. */
export function openUpscalersFor(appid: number): void {
  pending = appid;
  writeActiveTab(SECTION_ID);
  setShellMode("detail");
  listeners.forEach((listener) => listener());
  try {
    Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
    // The Decky tab must mount before its loader state can show Panel; a slow cold open
    // still lands on Panel on the second try, else the user sees the plugin list.
    setTimeout(() => setActivePlugin(PLUGIN_IDENTITY_NAME), 150);
    setTimeout(() => setActivePlugin(PLUGIN_IDENTITY_NAME), 500);
  } catch {
    /* navigation unavailable */
  }
}
