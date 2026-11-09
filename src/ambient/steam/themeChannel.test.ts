// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { AmbientThemeChannel, normalizeAppId } from "./themeChannel";

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

  it("a theme reports its selected game and releasing hands it back to Steam's carousel", () => {
    const channel = new AmbientThemeChannel();
    const changed = vi.fn();
    channel.onSelectionChanged(changed);
    expect(channel.themeSelection()).toBeUndefined();
    const first = channel.select("hooandee-duo", "1669420");
    expect(channel.themeSelection()).toEqual({ themeId: "hooandee-duo", appid: "1669420" });
    channel.select("hooandee-duo", "1669420");
    expect(changed).toHaveBeenCalledTimes(1);
    const second = channel.select("hooandee-duo", null);
    expect(channel.themeSelection()).toEqual({ themeId: "hooandee-duo", appid: null });
    first();
    expect(channel.themeSelection()?.appid).toBeNull();
    second();
    expect(channel.themeSelection()).toBeUndefined();
    expect(changed).toHaveBeenCalledTimes(3);
  });

  it("accepts only real Steam app ids, shortcuts included", () => {
    expect(normalizeAppId("3221225472")).toBe("3221225472");
    expect(normalizeAppId(570)).toBe("570");
    for (const bad of ["0", "-1", "abc", "4294967296", "1.5", "", null, undefined, {}]) expect(normalizeAppId(bad)).toBeNull();
  });
});
