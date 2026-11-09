type Listener = () => void;
type Entry = { openedAt: number; value?: string; selected: boolean; opener: boolean };
const entries = new Map<string, Entry>();
const listeners = new Map<string, Set<Listener>>();
const MAX_AGE = 120_000;

function entry(controlId: string): Entry | undefined {
  const value = entries.get(controlId);
  if (value && Date.now() - value.openedAt > MAX_AGE) {
    entries.delete(controlId);
    return undefined;
  }
  return value;
}

export function openDuoDropdown(controlId: string): void {
  entries.set(controlId, { openedAt: Date.now(), selected: false, opener: true });
}

export function selectDuoDropdown(controlId: string, value: string): void {
  const pending = entry(controlId);
  if (!pending || pending.selected) return;
  pending.selected = true;
  pending.value = value;
  for (const listener of listeners.get(controlId) ?? []) listener();
}

export function takeDuoSelection(controlId: string): string | undefined {
  const pending = entry(controlId);
  const value = pending?.value;
  if (pending) delete pending.value;
  return value;
}

export function hasDuoOpener(controlId: string): boolean {
  return entry(controlId)?.opener ?? false;
}

export function takeDuoOpener(controlId: string): boolean {
  const pending = entry(controlId);
  if (!pending?.opener) return false;
  pending.opener = false;
  return true;
}

export function subscribeDuoDropdown(controlId: string, listener: Listener): () => void {
  const set = listeners.get(controlId) ?? new Set<Listener>();
  set.add(listener);
  listeners.set(controlId, set);
  return () => {
    set.delete(listener);
    if (!set.size) listeners.delete(controlId);
  };
}
