import { useEffect, useState } from "react";

// Steam's own interface takes gamescope focus as this app id.
const STEAM_UI_APPID = 769;

interface Subscribable { Value?: unknown; Subscribe?(listener: (value: unknown) => void): { Unregister?(): void } | undefined }
interface CompositionStore { GetCurrentlyFocusedAppidSubscribableValue?(): Subscribable | undefined }

function focusedValue(): Subscribable | null {
  try {
    const store = (globalThis as { SteamUIStore?: { WindowStore?: { GamepadUIMainWindowInstance?: { m_CompositionStateStore?: CompositionStore } } } })
      .SteamUIStore?.WindowStore?.GamepadUIMainWindowInstance?.m_CompositionStateStore;
    return store?.GetCurrentlyFocusedAppidSubscribableValue?.() ?? null;
  } catch {
    return null;
  }
}

/** Whether the game, not Steam's interface, is what gamescope shows; unknown counts as in front. */
export function useGameInFront(): boolean {
  const [front, setFront] = useState(() => focusedValue()?.Value !== STEAM_UI_APPID);
  useEffect(() => {
    const value = focusedValue();
    if (!value) return;
    const update = (next: unknown) => setFront(next !== STEAM_UI_APPID);
    update(value.Value);
    const subscription = value.Subscribe?.(update);
    if (subscription?.Unregister) return () => subscription.Unregister?.();
    const timer = window.setInterval(() => update(value.Value), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return front;
}
