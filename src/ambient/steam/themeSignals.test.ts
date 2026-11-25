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

  it("does not attribute a native painter to a cosmetic loader or change live CSSOM", () => {
    surface("BackgroundGlass", { backgroundImage: "linear-gradient(black, gray)" });
    const style = loaderStyle(".volume-label { display: none }");
    const setDisabled = vi.fn();
    Object.defineProperty(style.sheet!, "disabled", { get: () => false, set: setDisabled });
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
    expect(setDisabled).not.toHaveBeenCalled();
  });

  it("keeps a loader painter confident with an extra native painter", () => {
    surface("ScrollArea", {});
    surface("BackgroundGlass", { backgroundImage: "linear-gradient(black, gray)" });
    loaderStyle(".h-ScrollArea { background-image: linear-gradient(red, blue) }");
    expect(detectThirdParty(document)).toEqual({ confidence: "high", id: "css:ScrollArea", candidates: ["css:ScrollArea"] });
  });

  it("does not attribute a loader background overridden by native inline paint", () => {
    surface("ScrollArea", {backgroundColor:"rgb(1, 2, 3)"});
    loaderStyle(".h-ScrollArea {background-color:rgb(10, 20, 30)}");
    expect(detectThirdParty(document)).toEqual({confidence:"none"});
  });

  it("keeps unresolved loader variables low confidence", () => {
    surface("ScrollArea", {backgroundColor:"rgb(1, 2, 3)"});
    loaderStyle(".h-ScrollArea {background-color:var(--theme-background)}");
    expect(detectThirdParty(document).confidence).toBe("low");
  });

  it("ignores loader paint in inactive media", () => {
    surface("ScrollArea", {backgroundColor:"rgb(1, 2, 3)"});
    loaderStyle("@media (min-width: 99999px) {.h-ScrollArea {background-color:rgb(1, 2, 3)}}");
    expect(detectThirdParty(document)).toEqual({confidence:"none"});
  });

  it("does not claim a value equally explained by native CSS", () => {
    surface("ScrollArea", {backgroundColor:"rgb(10, 20, 30)"});
    loaderStyle(".h-ScrollArea {background-color:rgb(10, 20, 30)}");
    expect(detectThirdParty(document).confidence).toBe("low");
  });

  it("attributes a matching pseudo-element without borrowing element or other-pseudo declarations", () => {
    const el = surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea::before {background-image:linear-gradient(red, blue)}');
    const nativeGet = window.getComputedStyle.bind(window);
    const before = document.createElement("span").style;
    Object.assign(before, {backgroundImage:"linear-gradient(red, blue)", content:'""', position:"fixed"});
    const absent = document.createElement("span").style; absent.content = "none";
    vi.spyOn(window, "getComputedStyle").mockImplementation((node, part) => node === el && part ? (part === "::before" ? before : absent) : nativeGet(node));
    expect(detectThirdParty(document)).toEqual({confidence:"high",id:"css:ScrollArea::before",candidates:["css:ScrollArea::before"]});
  });

  it("matches functional selector lists without mistaking their commas for branches", () => {
    surface("ScrollArea", {});
    loaderStyle(':is(.missing, .h-ScrollArea) {background-color:rgb(10, 20, 30)}');
    expect(detectThirdParty(document).confidence).toBe("high");
  });

  it("keeps unresolved native variables from granting high confidence", () => {
    surface("ScrollArea", {});
    const native = document.createElement("style");
    native.textContent = '.h-ScrollArea {background-color:var(--native-paint)}'; document.head.append(native);
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)}');
    expect(detectThirdParty(document).confidence).toBe("low");
  });

  it("does not let unrelated native functional selectors downgrade a literal loader painter", () => {
    surface("ScrollArea", {});
    const native = document.createElement("style");
    native.textContent = ':is(.unrelated, .other) {background-color:var(--native-paint)}'; document.head.append(native);
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)}');
    expect(detectThirdParty(document).confidence).toBe("high");
  });

  it("does not claim high confidence when native all can inherit the same paint", () => {
    surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)}');
    const native = document.createElement("style");
    native.textContent = '.h-ScrollArea {all:inherit!important}'; document.head.append(native);
    expect(detectThirdParty(document).confidence).not.toBe("high");
  });

  it("does not attribute Loader all-only inheritance as its own background", () => {
    surface("ScrollArea", {backgroundColor:"rgb(10, 20, 30)"});
    loaderStyle('.h-ScrollArea {all:inherit!important}');
    expect(detectThirdParty(document)).toEqual({confidence:"none"});
  });

  it("keeps a Loader declaration combined with all ambiguous", () => {
    surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30);all:inherit!important}');
    expect(detectThirdParty(document).confidence).not.toBe("high");
  });

  it("does not grant high confidence when a separate Loader all rule resets its literal background", () => {
    surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)} .h-ScrollArea {all:inherit!important}');
    expect(detectThirdParty(document).confidence).not.toBe("high");
  });

  it("does not grant high confidence when adopted styles cannot be inspected", () => {
    surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)}');
    // Keep the computed-style fixture independent of happy-dom's internal stylesheet traversal.
    const resolved = document.createElement("span").style;
    resolved.backgroundColor = "rgb(10, 20, 30)"; resolved.content = "none";
    vi.spyOn(window, "getComputedStyle").mockReturnValue(resolved);
    vi.spyOn(document, "adoptedStyleSheets", "get").mockImplementation(() => { throw Error("unreadable"); });
    expect(detectThirdParty(document).confidence).toBe("low");
  });

  it("reads adopted native sheets before attributing the same background to Loader", () => {
    surface("ScrollArea", {});
    loaderStyle('.h-ScrollArea {background-color:rgb(10, 20, 30)}');
    const adopted = new CSSStyleSheet();
    adopted.replaceSync('.h-ScrollArea {background-color:rgb(10, 20, 30)!important}');
    const getter = vi.spyOn(document, "adoptedStyleSheets", "get").mockReturnValue([adopted]);
    expect(detectThirdParty(document).confidence).toBe("low");
    getter.mockRestore();
  });

  it("resolves loader backgrounds without disabling sheets or changing their rules", () => {
    const el = surface("ScrollArea", {});
    const style = loaderStyle(".h-ScrollArea { background-color: rgb(10, 20, 30) }");
    const sheet = style.sheet!;
    const originalRules = Array.from(sheet.cssRules, rule => rule.cssText);
    const setDisabled = vi.fn();
    Object.defineProperty(sheet, "disabled", { get: () => false, set: setDisabled });
    expect(window.getComputedStyle(el).backgroundColor).toBe("rgb(10, 20, 30)");
    expect(detectThirdParty(document).id).toBe("css:ScrollArea");
    expect(setDisabled).not.toHaveBeenCalled();
    expect(Array.from(sheet.cssRules, rule => rule.cssText)).toEqual(originalRules);
    expect(window.getComputedStyle(el).backgroundColor).toBe("rgb(10, 20, 30)");
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

  it("stays silent without enabling a disabled loader stylesheet", () => {
    surface("ScrollArea", { backgroundColor: "rgb(10, 20, 30)" });
    const style = loaderStyle(".h-ScrollArea { background: red }");
    const setDisabled = vi.fn();
    Object.defineProperty(style.sheet!, "disabled", { get: () => true, set: setDisabled });
    expect(detectThirdParty(document)).toEqual({ confidence: "none" });
    expect(style.sheet!.disabled).toBe(true);
    expect(setDisabled).not.toHaveBeenCalled();
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
