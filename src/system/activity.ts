// User-activity signal from SteamClient. Steam already computes active/idle and
// emits on transitions via WebChat.RegisterForComputerActiveStateChange(state, ts)
// where state 1 = active, 2 = idle (CDP-validated on Legion Go 2: flips to idle
// ~4 s after the last input, and catches BOTH buttons and touch). We use it to
// drive download mode's ambient screen dim. Never throws; returns null when the
// API is absent so callers degrade.
export function subscribeActive(cb: (active: boolean) => void): (() => void) | null {
  try {
    const chat = SteamClient?.WebChat as
      | { RegisterForComputerActiveStateChange?: (cb: (state: number, ts: number) => void) => { unregister?: () => void } }
      | undefined;
    if (!chat || typeof chat.RegisterForComputerActiveStateChange !== "function") return null;
    const reg = chat.RegisterForComputerActiveStateChange((state) => cb(state === 1));
    return () => {
      try {
        reg?.unregister?.();
      } catch {
        /* ignore */
      }
    };
  } catch {
    return null;
  }
}
