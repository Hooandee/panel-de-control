// Section availability rules shared by the shell (ControlCenter) and the
// customization editor, so a section the user can't actually use never shows up
// in either place.
import { DeviceInfo } from "../api";
import { ListPref } from "../customize/layout";
import { blockOrder } from "../customize/manifest";

// Sections whose whole content is blocks (no fixed core): hiding every block
// leaves an empty tab, so the tab itself disappears. Potencia is excluded — it
// keeps its fixed power-arc core even with its blocks hidden.
const FULLY_MODULAR = new Set(["system", "display", "fans", "mandos"]);

/** A section the device can't use at all → never list it (shell nor editor).
 *  Controller management isn't offered on the Steam Deck (native gamepad +
 *  Steam Input own it). */
export function sectionHiddenOnDevice(device: DeviceInfo | null, id: string): boolean {
  if (id === "mandos") return !!device && device.key.startsWith("steam_deck");
  return false;
}

/** True when a fully-modular section has every one of its blocks hidden by the
 *  user → the tab would be empty, so hide the parent tab (recoverable from the
 *  editor, which still lists it). */
export function allBlocksHidden(id: string, blocks: Record<string, ListPref>): boolean {
  if (!FULLY_MODULAR.has(id)) return false;
  const ids = blockOrder(id);
  if (!ids.length) return false;
  const hidden = new Set(blocks[id]?.hidden ?? []);
  return ids.every((b) => hidden.has(b));
}
