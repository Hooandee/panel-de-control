export interface ShortcutHint {
  exe: string;
  dir: string;
  name: string;
}

interface ShortcutDetails {
  strShortcutExe?: string;
  strShortcutStartDir?: string;
}

const w = window as unknown as {
  SteamClient?: { Apps?: { RegisterForAppDetails?: (appid: number, cb: (d: ShortcutDetails) => void) => { unregister: () => void } } };
};

/** Where Steam itself says a non-Steam shortcut points; shortcuts.vdf is not always written. */
export function readShortcutHint(appid: number, name: string, timeoutMs = 1500): Promise<ShortcutHint | null> {
  return new Promise((resolve) => {
    const register = w.SteamClient?.Apps?.RegisterForAppDetails;
    if (typeof register !== "function") return resolve(null);
    let handle: { unregister: () => void } | null = null;
    const timer = window.setTimeout(() => {
      handle?.unregister();
      resolve(null);
    }, timeoutMs);
    try {
      handle = register(appid, (details) => {
        window.clearTimeout(timer);
        handle?.unregister();
        resolve(details?.strShortcutExe ? { exe: details.strShortcutExe, dir: details.strShortcutStartDir ?? "", name } : null);
      });
    } catch {
      window.clearTimeout(timer);
      resolve(null);
    }
  });
}
