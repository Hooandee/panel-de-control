// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { AudioLoaderBridge } from "./audioLoader";

function music(paused: boolean) {
  const el = document.createElement("audio");
  let isPaused = paused;
  Object.defineProperty(el, "paused", { get: () => isPaused });
  vi.spyOn(el, "pause").mockImplementation(() => { isPaused = true; });
  vi.spyOn(el, "play").mockImplementation(async () => { isPaused = false; });
  return el;
}

describe("AudioLoaderBridge", () => {
  it("is inactive without Audio Loader", () => {
    expect(new AudioLoaderBridge({}).isActive()).toBe(false);
  });

  it("pauses playing menu music and restores only what it paused", () => {
    const el = music(false);
    const bridge = new AudioLoaderBridge({ AUDIOLOADER_MENUMUSIC: el });
    expect(bridge.isActive()).toBe(true);
    bridge.yieldToPanel();
    expect(el.paused).toBe(true);
    expect(bridge.isActive()).toBe(true);
    bridge.restore();
    expect(el.paused).toBe(false);
  });

  it("never starts music the user had stopped", () => {
    const el = music(true);
    const bridge = new AudioLoaderBridge({ AUDIOLOADER_MENUMUSIC: el });
    bridge.yieldToPanel();
    bridge.restore();
    expect(el.play).not.toHaveBeenCalled();
  });
});
