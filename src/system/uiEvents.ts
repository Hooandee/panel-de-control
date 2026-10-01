/** Steam settings Panel's interface writes directly (overlay level, volume,
 * brightness, per-game profile, launch options), sent to the backend diary.
 * The sink is attached at plugin start so this module never loads the Decky API;
 * without it every call is a no-op. Repeats of one action within the window
 * (a dragged slider) go out once, with the last value. */
export type UiEventSink = (area: string, action: string, detail: string, ok: boolean) => unknown;

const COALESCE_MS = 1000;
let sink: UiEventSink | null = null;
const pending = new Map<string, { timer: ReturnType<typeof setTimeout>; send: () => void }>();

export function setUiEventSink(next: UiEventSink | null): void {
  for (const entry of pending.values()) {
    clearTimeout(entry.timer);
    entry.send();
  }
  pending.clear();
  sink = next;
}

export function recordUiEvent(area: string, action: string, fields: Record<string, unknown>, ok = true): void {
  const target = sink;
  if (!target) return;
  let detail: string;
  try {
    detail = JSON.stringify(fields).slice(0, 400);
  } catch {
    detail = "";
  }
  const send = () => {
    try {
      void Promise.resolve(target(area, action, detail, ok)).catch(() => undefined);
    } catch {}
  };
  const key = `${area}:${action}`;
  const previous = pending.get(key);
  if (previous) clearTimeout(previous.timer);
  const timer = setTimeout(() => {
    pending.delete(key);
    send();
  }, COALESCE_MS);
  pending.set(key, { timer, send });
}
