// The last active tab, persisted in localStorage. Decky remounts the panel on
// each QAM open — and some actions (e.g. applying a controller remap reloads the
// virtual gamepad, which makes Steam remount the panel) — so without this the
// shell would snap back to the first tab. Pure UI preference, no backend. Never
// throws; degrades to "no memory" if storage is unavailable.
const KEY = "pdc:activeTab";

export function readActiveTab(): string | null {
  try {
    return window.localStorage?.getItem(KEY) ?? null;
  } catch {
    return null;
  }
}

export function writeActiveTab(id: string): void {
  try {
    window.localStorage?.setItem(KEY, id);
  } catch {
    /* storage unavailable — active tab just won't persist */
  }
}
