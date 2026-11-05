// Steam shows every menu and dialog opened from the QAM in the main window: it closes the
// QAM and mounts the panel again when they close, so the open game page and a choice not yet
// applied would be lost. Openers hold the page here first; the next mount takes it back.

export interface PageDraft<C = unknown> {
  mode: "easy" | "custom";
  choice: C;
}

type Listener = (draft: PageDraft) => void;

const HOLD_MS = 2 * 60_000;

let shown: number | null = null;
let draft: { appid: number; value: PageDraft } | null = null;
let held: { appid: number; until: number } | null = null;
const listeners = new Map<number, Set<Listener>>();

export function showGame(appid: number | null): void {
  if (appid !== shown) draft = null;
  shown = appid;
  if (appid === null || appid !== held?.appid) held = null;
}

export function writeDraft(appid: number, value: PageDraft): void {
  draft = { appid, value };
  for (const listener of listeners.get(appid) ?? []) listener(value);
}

export function onDraft(appid: number, listener: Listener): () => void {
  const set = listeners.get(appid) ?? new Set<Listener>();
  set.add(listener);
  listeners.set(appid, set);
  return () => {
    set.delete(listener);
    if (set.size === 0) listeners.delete(appid);
  };
}

export function holdPage(): void {
  if (shown !== null) held = { appid: shown, until: Date.now() + HOLD_MS };
}

export function takeHeldPage(): { appid: number; draft: PageDraft | null } | null {
  // Not consumed: some Decky builds mount the panel twice while the menu closes, and the first mount would
  // leave the second with the list. Leaving the page (showGame) or the timeout clears it.
  const page = held;
  if (!page || Date.now() > page.until) return null;
  return { appid: page.appid, draft: draft?.appid === page.appid ? draft.value : null };
}

export function releasePage(): void {
  shown = null;
  draft = null;
  held = null;
}
