// Pure policy for mirroring frontend UI preferences to the durable backend.

const LANG_KEY = "panel-de-control-lang"; // predates the pdc: namespace
const EPHEMERAL = new Set<string>(["pdc:activeTab"]); // not persisted across reboots

export function isDurableKey(key: string): boolean {
  if (EPHEMERAL.has(key)) return false;
  return key === LANG_KEY || key.startsWith("pdc:");
}

// Reconcile the backend copy with the local cache: heal = write into
// localStorage (backend wins); migrate = push a local-only key up so a
// pre-existing choice survives the first reboot after upgrade.
export function planPrefsSync(
  backend: Record<string, string>,
  local: Record<string, string>,
): { heal: Record<string, string>; migrate: Record<string, string> } {
  const heal: Record<string, string> = {};
  for (const [k, v] of Object.entries(backend)) {
    if (isDurableKey(k)) heal[k] = v;
  }
  const migrate: Record<string, string> = {};
  for (const [k, v] of Object.entries(local)) {
    if (isDurableKey(k) && !(k in heal)) migrate[k] = v;
  }
  return { heal, migrate };
}
