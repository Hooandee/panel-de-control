// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { theme, themed } from "../theme";
import { applyThemeTokens, parseThemeColor, parseThemeRadius, readThemeTokens } from "./themeTokens";

afterEach(() => {
  applyThemeTokens({ color: {}, radius: {} });
  document.documentElement.removeAttribute("style");
});

describe("theme tokens", () => {
  it("accepts only plain colours and small pixel radii", () => {
    expect(parseThemeColor(" #2b2b2d ")).toBe("#2b2b2d");
    expect(parseThemeColor("rgba(255, 255, 255, .5)")).toBe("rgba(255, 255, 255, .5)");
    expect(parseThemeColor("var(--x)")).toBeNull();
    expect(parseThemeColor("red; background: url(x)")).toBeNull();
    expect(parseThemeRadius("12px")).toBe(12);
    expect(parseThemeRadius("6")).toBe(6);
    expect(parseThemeRadius("1em")).toBeNull();
  });

  it("reads what a theme publishes on :root and ignores the rest", () => {
    const root = document.documentElement;
    root.style.setProperty("--pdc-theme-surface-raised", "#2b2b2d");
    root.style.setProperty("--pdc-theme-text", "nonsense");
    root.style.setProperty("--pdc-theme-radius-md", "12px");
    expect(readThemeTokens(document)).toEqual({ color: { surfaceRaised: "#2b2b2d" }, radius: { md: 12 } });
  });

  it("keeps Panel's own look without a theme and follows one when present", () => {
    expect(theme.card.background).toBe("#0c0c10");
    expect(theme.radius.md).toBe(14);
    const style = themed(() => ({ background: theme.color.surfaceRaised, borderRadius: theme.radius.md }));
    Object.freeze(style);
    applyThemeTokens({ color: { surfaceRaised: "#2b2b2d" }, radius: { md: 12 } });
    expect(theme.card).toMatchObject({ background: "#2b2b2d", borderRadius: 12 });
    expect({ ...style }).toEqual({ background: "#2b2b2d", borderRadius: 12 });
  });
});
