import { afterEach, describe, expect, it, vi } from "vitest";

import { subscribeVirtualKeyboard } from "./virtualKeyboard";

function steamKeyboard(initial: boolean) {
  const callbacks = new Set<() => void>();
  const value = {
    Value: initial,
    Subscribe: (callback: () => void) => {
      callbacks.add(callback);
      return { Unsubscribe: () => callbacks.delete(callback) };
    },
  };
  vi.stubGlobal("SteamUIStore", { ActiveWindowInstance: { VirtualKeyboardManager: { IsShowingVirtualKeyboard: value } } });
  return {
    set(showing: boolean) {
      value.Value = showing;
      callbacks.forEach((callback) => callback());
    },
    callbacks,
  };
}

describe("subscribeVirtualKeyboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reports Steam's keyboard now and on every change, and lets go on unsubscribe", () => {
    const keyboard = steamKeyboard(true);
    const seen: boolean[] = [];
    const stop = subscribeVirtualKeyboard((showing) => seen.push(showing));
    keyboard.set(false);
    keyboard.set(true);
    stop();
    keyboard.set(false);
    expect(seen).toEqual([true, false, true]);
    expect(keyboard.callbacks.size).toBe(0);
  });

  it("reads as hidden without Steam's keyboard manager", () => {
    vi.stubGlobal("SteamUIStore", undefined);
    const seen: boolean[] = [];
    subscribeVirtualKeyboard((showing) => seen.push(showing))();
    expect(seen).toEqual([false]);
  });
});
