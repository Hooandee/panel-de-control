// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { THEME_ACCENT_ID, applyAccentId, applyThemeAccent, currentAccentHex, DEFAULT_ACCENT } from "./accentColor";
import { watchThemeAccent } from "./themeAccent";

const frame = () => new Promise((resolve) => setTimeout(resolve, 30));

describe("theme accent watcher", () => {
  afterEach(() => {
    document.head.innerHTML = "";
    applyThemeAccent(null);
  });

  it("adopts the colour a theme stylesheet publishes and drops it when the sheet goes", async () => {
    applyAccentId(THEME_ACCENT_ID);
    const stop = watchThemeAccent(document);
    expect(currentAccentHex()).toBe(DEFAULT_ACCENT.hex);
    const style = document.createElement("style");
    style.textContent = ":root { --pdc-theme-accent: 95, 242, 176; }";
    document.head.append(style);
    await frame();
    expect(currentAccentHex()).toBe("#5ff2b0");
    style.remove();
    await frame();
    expect(currentAccentHex()).toBe(DEFAULT_ACCENT.hex);
    stop();
  });
});
