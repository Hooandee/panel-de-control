// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { theme, themed } from "../theme";
import { applyThemeTokens, parseThemeColor, parseThemeRadius, readThemeTokens } from "./themeTokens";

afterEach(() => {
  vi.restoreAllMocks();
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
    root.style.setProperty("--pdc-theme-stroke", "2.5px");
    expect(readThemeTokens(document)).toEqual({ color: { surfaceRaised: "#2b2b2d" }, radius: { md: 12 }, size: { stroke: 2.5 } });
  });

  it("keeps Panel's own look without a theme and follows one when present", () => {
    expect(theme.card.background).toBe("#0c0c10");
    expect(theme.radius.md).toBe(14);
    const style = themed(() => ({ background: theme.color.surfaceRaised, borderRadius: theme.radius.md }));
    Object.freeze(style);
    applyThemeTokens({ color: { surfaceRaised: "#2b2b2d" }, radius: { md: 12 } });
    expect(theme.card).toMatchObject({ background: "#2b2b2d", borderRadius: 12 });
    expect({ ...style }).toEqual({ background: "#2b2b2d", borderRadius: 12 });
    applyThemeTokens({ color: { outline: "transparent", selectedFill: "#3a3a3c" }, radius: {}, labelTransform: "none" });
    expect(theme.card.boxShadow).toBe("inset 0 0 0 1px transparent");
    expect(theme.color.hairline).toBe("rgba(255,255,255,0.06)");
    expect(theme.color.selectedFill).toBe("#3a3a3c");
    expect(theme.sectionLabel).toMatchObject({ textTransform: "none", letterSpacing: 0 });
  });
});

 it("keeps numeric fonts live, including arithmetic and section headings", () => {
  expect({ ...theme.font }).toEqual({ caption: 11, body: 13, value: 28 });
  const cached = themed(() => ({ fontSize: theme.font.caption - 1 }));
  applyThemeTokens({ color: {}, radius: {}, size: { fontCaption: 18, fontBody: 23, fontValue: 43 } });
  expect({ ...theme.font }).toEqual({ caption: 18, body: 23, value: 43 });
  expect(theme.sectionLabel.fontSize).toBe(18);
  expect(cached.fontSize).toBe(17);
  applyThemeTokens({ color: {}, radius: {} });
  expect(theme.sectionLabel.fontSize).toBe(11);
  expect(cached.fontSize).toBe(10);
 });

 it("reads positive font pixels and ignores missing or invalid typography", () => {
  const root = document.documentElement;
  root.style.setProperty("--pdc-theme-font-caption", "18.5px");
  root.style.setProperty("--pdc-theme-font-body", "23");
  root.style.setProperty("--pdc-theme-font-value", "0px");
  expect(readThemeTokens(document).size).toEqual({ fontCaption: 18.5, fontBody: 23 });
  for (const invalid of ["-1px", "inherit", "initial", "nonsense", "NaN", "Infinity"]) {
    root.style.setProperty("--pdc-theme-font-caption", invalid);
    expect(readThemeTokens(document).size?.fontCaption).toBeUndefined();
  }
 });

 it("uses the browser's resolved font pixels for viewport expressions and removes probes", () => {
  document.documentElement.style.setProperty("--pdc-theme-font-caption", "calc(100vh / 50)");
  document.documentElement.style.setProperty("--pdc-theme-font-body", "2vh");
  const computed = window.getComputedStyle.bind(window);
  const before = document.documentElement.children.length;
  // happy-dom does not resolve viewport calc(); model the browser's computed readback.
  vi.spyOn(window, "getComputedStyle").mockImplementation((element, pseudo) => {
    if (element instanceof HTMLElement && element.style.fontSize === "calc(100vh / 50)") return { fontSize: "18px" } as CSSStyleDeclaration;
    if (element instanceof HTMLElement && element.style.fontSize === "2vh") return { fontSize: "18px" } as CSSStyleDeclaration;
    return computed(element, pseudo);
  });
  expect(readThemeTokens(document).size).toEqual({ fontCaption: 18, fontBody: 18 });
  expect(document.documentElement.children.length).toBe(before);
 });
