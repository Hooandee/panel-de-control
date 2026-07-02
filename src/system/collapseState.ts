// Per-section collapse state, persisted in localStorage so a card stays collapsed
// across QAM reopens. Pure UI preference → no backend round-trip. Never throws;
// if storage is unavailable it just degrades to "always open".
const KEY = (id: string) => `pdc:collapsed:${id}`;

/** True if the section `id` was left collapsed. Defaults to false (open). */
export function isCollapsed(id: string): boolean {
  try {
    return window.localStorage?.getItem(KEY(id)) === "1";
  } catch {
    return false;
  }
}

export function setCollapsed(id: string, collapsed: boolean): void {
  try {
    window.localStorage?.setItem(KEY(id), collapsed ? "1" : "0");
  } catch {
    /* storage unavailable — collapse just won't persist */
  }
}
