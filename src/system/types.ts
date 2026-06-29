/**
 * A scalar system control backed by SteamClient (brightness, volume). Works in
 * the native 0..1 fraction. Adapters degrade gracefully: subscribe() returns
 * null when the underlying API is absent, so the UI can show a degraded state
 * instead of faking a value.
 */
export interface ScalarControl {
  /**
   * Subscribe to value changes (0..1). Steam fires the current value
   * immediately on subscribe, which seeds the initial reading. Returns an
   * unsubscribe function, or null if the API is unavailable.
   */
  subscribe: (cb: (fraction: number) => void) => (() => void) | null;
  /** Set the value (0..1). No-op if the API is unavailable. */
  set: (fraction: number) => void;
}

/** What a section consumes: integer percent + a percent setter + availability. */
export interface SystemControl {
  supported: boolean;
  percent: number;
  set: (percent: number) => void;
}
