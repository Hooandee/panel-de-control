import { readString, writeString } from "../system/pdcStorage";

// The last active tab. Decky remounts the panel on each QAM open — and some
// actions (e.g. applying a controller remap reloads the virtual gamepad, which
// makes Steam remount the panel) — so without this the shell would snap back to
// the first tab. Ephemeral by design: pdc:activeTab is in prefsSync's EPHEMERAL
// set, so it stays in localStorage only and is not mirrored to the backend.
const KEY = "pdc:activeTab";

export function readActiveTab(): string | null {
  return readString(KEY);
}

export function writeActiveTab(id: string): void {
  writeString(KEY, id);
}
