interface ShowingValue {
  Value?: boolean;
  Subscribe?: (callback: () => void) => { Unsubscribe?: () => void } | undefined;
}

interface SteamWindowStore {
  ActiveWindowInstance?: { VirtualKeyboardManager?: { IsShowingVirtualKeyboard?: ShowingValue } };
}

function showingValue(): ShowingValue | null {
  try {
    const store = (globalThis as { SteamUIStore?: SteamWindowStore }).SteamUIStore;
    return store?.ActiveWindowInstance?.VirtualKeyboardManager?.IsShowingVirtualKeyboard ?? null;
  } catch {
    return null;
  }
}

/**
 * Follows Steam's on-screen keyboard. Without Steam's value (other clients, older builds) it reports
 * the keyboard as hidden, so callers keep their previous behaviour.
 */
export function subscribeVirtualKeyboard(listener: (showing: boolean) => void): () => void {
  const value = showingValue();
  listener(!!value?.Value);
  let handle: { Unsubscribe?: () => void } | undefined;
  try {
    handle = value?.Subscribe?.(() => listener(!!value.Value));
  } catch {
    handle = undefined;
  }
  return () => {
    try {
      handle?.Unsubscribe?.();
    } catch {
      // Steam already tore the keyboard manager down.
    }
  };
}
