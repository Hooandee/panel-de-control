// plugin.json `name` = install folder = the label Decky renders in its plugin list
// (it overrides whatever `name` definePlugin returns and uses it as a lookup key, so
// the list can only be relabelled at the DOM). Must stay in sync with plugin.json.
export const PLUGIN_IDENTITY_NAME = "Panel de Control";

// Relabel only the exact identity row, and only when the target differs — so other
// plugins' rows and an already-localized row are left alone (the latter also stops
// our own write from re-triggering).
export function nextRowText(
  current: string,
  identity: string,
  target: string,
): string | null {
  if (current !== identity) return null;
  if (target === identity) return null;
  return target;
}
