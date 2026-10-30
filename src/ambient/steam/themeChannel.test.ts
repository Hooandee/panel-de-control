// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { AmbientThemeChannel } from "./themeChannel";

describe("AmbientThemeChannel", () => {
  it("tracks the active claim and notifies on change", () => {
    const channel = new AmbientThemeChannel();
    const changed = vi.fn();
    channel.onClaimsChanged(changed);
    const release = channel.claim("hooandee-gallery", { name: "Gallery", surfaces: ["home"], mode: "host" });
    expect(channel.activeClaim()).toMatchObject({ themeId: "hooandee-gallery", mode: "host" });
    release();
    release();
    expect(channel.activeClaim()).toBeNull();
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it("a stale release never drops a newer claim from the same theme", () => {
    const channel = new AmbientThemeChannel();
    const first = channel.claim("t", { name: "T", surfaces: ["home"], mode: "yield" });
    channel.claim("t", { name: "T", surfaces: ["home"], mode: "host" });
    first();
    expect(channel.activeClaim()?.mode).toBe("host");
  });

  it("publishes only real changes", () => {
    const channel = new AmbientThemeChannel();
    const listener = vi.fn();
    channel.subscribe(listener);
    const state = { owner: "panel" as const, media: { url: "u", kind: "image" as const }, motion: "play" as const };
    channel.publish(state);
    channel.publish({ ...state, media: { ...state.media } });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("shares Panel's frame only while Panel owns the background", () => {
    const channel = new AmbientThemeChannel();
    const frame = document.createElement("img");
    channel.setFrameSource(() => frame);
    expect(channel.frame()).toBeNull();
    channel.publish({ owner: "panel", media: { url: "u", kind: "image" }, motion: "play" });
    expect(channel.frame()).toBe(frame);
    channel.publish({ owner: "theme", media: null, motion: "play" });
    expect(channel.frame()).toBeNull();
  });
});
