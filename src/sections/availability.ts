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

/** True when a fully-modular section has nothing left to show → hide the parent
 *  tab (recoverable from the editor, which still lists it). "Nothing" means: it
 *  renders zero blocks on this machine, or every block it does render is hidden.
 *  `presentIds` (from the present registry) scopes the check to blocks that
 *  actually exist here; falls back to the manifest before the section has rendered. */
export function allBlocksHidden(
  id: string,
  blocks: Record<string, ListPref>,
  presentIds?: string[] | null,
): boolean {
  if (!FULLY_MODULAR.has(id)) return false;
  if (presentIds && presentIds.length === 0) return true; // renders nothing → empty
  const ids = presentIds && presentIds.length ? presentIds : blockOrder(id);
  if (!ids.length) return false;
  const hidden = new Set(blocks[id]?.hidden ?? []);
  return ids.every((b) => hidden.has(b));
}
