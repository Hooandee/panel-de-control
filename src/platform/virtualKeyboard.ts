/** Steam returns `Unsubscribe` from this value and `Unregister` from other subscribable values. */
interface Subscription {
  Unsubscribe?: () => void;
  Unregister?: () => void;
}

interface ShowingValue {
  Value?: boolean;
  Subscribe?: (callback: () => void) => Subscription | undefined;
}

interface SteamWindowStore {
  ActiveWindowInstance?: { VirtualKeyboardManager?: { IsShowingVirtualKeyboard?: ShowingValue } };
}

/** Steam's window can be missing at boot or replaced later (overlay, UI restart); the value is looked up again. */
const RECHECK_MS = 5000;

function showingValue(): ShowingValue | null {
  try {
    const store = (globalThis as { SteamUIStore?: SteamWindowStore }).SteamUIStore;
    return store?.ActiveWindowInstance?.VirtualKeyboardManager?.IsShowingVirtualKeyboard ?? null;
  } catch {
    return null;
  }
}

function release(handle: Subscription | undefined): void {
  try {
    if (handle?.Unsubscribe) handle.Unsubscribe();
    else handle?.Unregister?.();
  } catch {
    // Steam already tore the keyboard manager down.
  }
}

/**
 * Follows Steam's on-screen keyboard. Without Steam's value (other clients, older builds) it reports
 * the keyboard as hidden, so callers keep their previous behaviour.
 */
export function subscribeVirtualKeyboard(listener: (showing: boolean) => void): () => void {
  let value: ShowingValue | null | undefined;
  let handle: Subscription | undefined;
  let last: boolean | null = null;
  const report = (showing: boolean) => {
    if (showing === last) return;
    last = showing;
    listener(showing);
  };
  const attach = () => {
    const current = showingValue();
    if (current === value && (handle || !current)) return;
    release(handle);
    handle = undefined;
    value = current;
    report(!!current?.Value);
    try {
      // A Steam build that registers without returning a handle must not be subscribed again every check.
      handle = current?.Subscribe?.(() => report(!!current.Value)) ?? (current ? {} : undefined);
    } catch {
      handle = undefined;
    }
  };
  attach();
  const timer = setInterval(attach, RECHECK_MS);
  return () => {
    clearInterval(timer);
    release(handle);
  };
}
