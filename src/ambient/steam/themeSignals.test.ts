// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./steamClasses", () => ({ steamClass: (key: string) => `h-${key}` }));

import { applyNeutralizer, detectThirdParty, readThemeClaim } from "./themeSignals";

function surface(key: string, style: Partial<CSSStyleDeclaration>) {
  const el = document.createElement("div");
  el.className = `h-${key}`;
  Object.assign(el.style, style);
  el.getBoundingClientRect = () => ({ x: 0, y: 0, width: window.innerWidth, height: window.innerHeight, top: 0, left: 0, right: 0, bottom: 0, toJSON: () => ({}) });
  document.body.appendChild(el);
  return el;
}

function loaderStyle(css: string) {
  const style = document.createElement("style");
  style.className = "css-loader-style";
  style.textContent = css;
  document.head.append(style);
  let disabled = false;
  // happy-dom does not apply CSSStyleSheet.disabled to the cascade; emulate that browser boundary.
  Object.defineProperty(style.sheet!, "disabled", {
    get: () => disabled,
    set: (value: boolean) => { disabled = value; style.textContent = value ? "" : css; },
  });
  return style;
}

describe("theme signals", () => {
  afterEach(() => vi.restoreAllMocks());
  beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    document.documentElement.removeAttribute("style");
  });

  it("reads a cooperative claim from :root", () => {
    document.documentElement.style.setProperty("--pdc-ambient-claim", "hooandee-gallery");
    document.documentElement.style.setProperty("--pdc-ambient-claim-name", '"Gallery"');
    expect(readThemeClaim(document)).toEqual({ id: "hooandee-gallery", name: "Gallery" });
  });

  it("ignores missing or malformed claims", () => {
    expect(readThemeClaim(document)).toBeNull();
    document.documentElement.style.setProperty("--pdc-ambient-claim", "bad id!");
    expect(readThemeClaim(document)).toBeNull();
  });

  it("stays silent without CSS Loader styles", () => {
    surface("ScrollArea", { backgroundImage: "linear-gradient(red, blue)" });
    expect(detectThirdParty(document, false)).toEqual({ confidence: "none" });
  });

  it("one large painted surface is a confident third party", () => {
    surface("ScrollArea", {});
    loaderStyle(".h-ScrollArea { background-image: linear-gradient(red, blue) }");
    expect(detectThirdParty(document, true)).toEqual({ confidence: "high", id: "css:ScrollArea", candidates: ["css:ScrollArea"] });
  });

  it("does not blame native backgrounds on cosmetic CSS Loader styles", () => {
    surface("BackgroundGlass", { backgroundImage: "linear-gradient(black, gray)" });
    const style = document.createElement("style");
    style.className = "css-loader-style";
    style.textContent = ".volume-label { display: none }";
    document.head.append(style);
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
    expect(style.sheet?.disabled).not.toBe(true);
  });

  it("translucent surfaces are not painters", () => {
    surface("ScrollArea", {});
    loaderStyle(".h-ScrollArea { background-color: rgba(0, 0, 0, 0.3) }");
    expect(detectThirdParty(document, true)).toEqual({ confidence: "none" });
  });

  it("several painters are ambiguous", () => {
    surface("ScrollArea", {});
    surface("GamepadLibrary", {});
    loaderStyle(".h-ScrollArea { background-image: linear-gradient(red, blue) } .h-GamepadLibrary { background-color: rgb(10, 10, 10) }");
    expect(detectThirdParty(document, true).confidence).toBe("low");
  });

  it("ignores loader rules that leave the native background unchanged", () => {
    surface("BackgroundGlass", { backgroundColor: "rgb(10, 10, 10)" });
    loaderStyle(".h-BackgroundGlass { background-color: rgb(10, 10, 10) }");
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
  });

  it("does not enable a loader stylesheet that was already disabled", () => {
    surface("ScrollArea", {});
    const style = loaderStyle(".h-ScrollArea { background: red }");
    const sheet = style.sheet!;
    sheet.disabled = true;
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
    expect(sheet.disabled).toBe(true);
  });

  it("restores loader styles and stays uncertain if a baseline style cannot be read", () => {
    surface("ScrollArea", {});
    const style = loaderStyle(".h-ScrollArea { background: red }");
    const sheet = style.sheet!;
    const read = window.getComputedStyle.bind(window);
    vi.spyOn(window, "getComputedStyle").mockImplementation((element, pseudo) => {
      if (sheet.disabled) throw new Error("style unavailable");
      return read(element, pseudo);
    });
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
    expect(sheet.disabled).toBe(false);
    expect(style.textContent).toContain("background: red");
  });

  it("neutralizes only chosen painters, scoped to Panel owning the background", () => {
    applyNeutralizer(document, ["css:ScrollArea", "css:RecentGamesInnerContainer::before", "bogus"]);
    const css = document.getElementById("pdc-ambient-neutralize")?.textContent ?? "";
    expect(css).toContain(':root[data-pdc-ambient-background="panel"] .h-ScrollArea{background:none!important');
    expect(css).toContain(".h-RecentGamesInnerContainer::before{");
    expect(css).not.toContain("bogus");
    applyNeutralizer(document, []);
    expect(document.getElementById("pdc-ambient-neutralize")).toBeNull();
  });
});
