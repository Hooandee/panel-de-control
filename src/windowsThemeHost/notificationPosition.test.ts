import { afterEach, describe, expect, it, vi } from "vitest";

import { installOverlayToastPosition } from "./notificationPosition";

function positioned(position: number, horizontalInset = 0) {
  const window = {
    NotificationPosition: { position, horizontalInset, verticalInset: 0 },
    SetNotificationPosition: vi.fn((p: number, h: number, v: number) => { window.NotificationPosition = { position: p, horizontalInset: h, verticalInset: v }; }),
  };
  return window;
}

afterEach(() => { vi.useRealTimers(); });

describe("game overlay toast position on Windows", () => {
  it("puts every game overlay's toasts where Big Picture shows its own, and gives them back", () => {
    vi.useFakeTimers();
    const main = positioned(0, 12), first = positioned(3), overlays = new Map([[16160, first]]);
    let active = true;
    const scope = { SteamUIStore: { WindowStore: { GamepadUIMainWindowInstance: main, m_mapOverlayPopupByPID: overlays } } } as unknown as typeof globalThis;
    const stop = installOverlayToastPosition(scope, () => active);
    expect(first.NotificationPosition).toEqual({ position: 0, horizontalInset: 12, verticalInset: 0 });

    const second = positioned(3); overlays.set(20412, second);
    vi.advanceTimersByTime(1_000);
    expect(second.NotificationPosition.position).toBe(0);

    active = false;
    vi.advanceTimersByTime(1_000);
    expect(first.NotificationPosition.position).toBe(3);
    expect(second.NotificationPosition.position).toBe(3);
    stop();
  });
});
