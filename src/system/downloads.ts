// Steam's download queue as one boolean. `paused` flickers true while idle, so only the state counts. Never throws; null when the API is absent.
interface DownloadOverview {
  update_state?: string;
}

export function subscribeDownloadActive(cb: (active: boolean) => void): (() => void) | null {
  try {
    const downloads = SteamClient?.Downloads as
      | { RegisterForDownloadOverview?: (cb: (o: DownloadOverview) => void) => { unregister?: () => void } }
      | undefined;
    if (!downloads || typeof downloads.RegisterForDownloadOverview !== "function") return null;
    const reg = downloads.RegisterForDownloadOverview((o) => cb(o.update_state !== "None"));
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
