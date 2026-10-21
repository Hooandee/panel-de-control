// On the Deck a running game's notifications come through Big Picture's window, so they appear where Big Picture puts
// its toasts (a theme can move them, as Duo does to the top left). On Windows each game has its own overlay window with
// its own toast position (bottom right by default), so a friend coming online showed up in the opposite corner.
// While a theme runtime is mounted every game overlay takes Big Picture's toast position, and gets its own back after.

const POLL_MS = 1_000;

interface ToastPosition {
  position?: number;
  horizontalInset?: number;
  verticalInset?: number;
}

interface PositionedWindow {
  NotificationPosition?: ToastPosition;
  SetNotificationPosition?(position: number, horizontalInset: number, verticalInset: number): void;
}

interface PositionScope {
  SteamUIStore?: {
    WindowStore?: {
      GamepadUIMainWindowInstance?: PositionedWindow;
      m_mapOverlayPopupByPID?: { values?(): Iterable<PositionedWindow> };
    };
  };
}

const same = (a: ToastPosition | undefined, b: ToastPosition) =>
  a?.position === b.position && (a?.horizontalInset ?? 0) === (b.horizontalInset ?? 0) && (a?.verticalInset ?? 0) === (b.verticalInset ?? 0);

export function installOverlayToastPosition(
  scope: typeof globalThis,
  isActive: () => boolean,
  timers: Pick<typeof globalThis, "setInterval" | "clearInterval"> = globalThis,
): () => void {
  const steam = scope as unknown as PositionScope;
  const original = new Map<PositionedWindow, Required<ToastPosition>>();

  const restore = (overlay: PositionedWindow) => {
    const own = original.get(overlay);
    if (!own) return;
    original.delete(overlay);
    try {
      overlay.SetNotificationPosition?.(own.position, own.horizontalInset, own.verticalInset);
    } catch {
      // The game closed with its overlay.
    }
  };

  const sync = () => {
    const store = steam.SteamUIStore?.WindowStore;
    const target = store?.GamepadUIMainWindowInstance?.NotificationPosition;
    const overlays = [...(store?.m_mapOverlayPopupByPID?.values?.() ?? [])];
    for (const overlay of [...original.keys()]) if (!overlays.includes(overlay)) original.delete(overlay);
    if (!isActive() || typeof target?.position !== "number") {
      for (const overlay of [...original.keys()]) restore(overlay);
      return;
    }
    for (const overlay of overlays) {
      const current = overlay.NotificationPosition;
      if (!overlay.SetNotificationPosition || typeof current?.position !== "number" || same(current, target)) continue;
      if (!original.has(overlay)) {
        original.set(overlay, { position: current.position, horizontalInset: current.horizontalInset ?? 0, verticalInset: current.verticalInset ?? 0 });
      }
      try {
        overlay.SetNotificationPosition(target.position, target.horizontalInset ?? 0, target.verticalInset ?? 0);
      } catch {
        // Steam rebuilt the overlay; the next poll sees the new one.
      }
    }
  };

  sync();
  const poll = timers.setInterval(sync, POLL_MS);
  return () => {
    timers.clearInterval(poll);
    for (const overlay of [...original.keys()]) restore(overlay);
  };
}
