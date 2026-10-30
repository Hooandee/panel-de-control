// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

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

describe("theme signals", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
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
    surface("ScrollArea", { backgroundImage: "linear-gradient(red, blue)" });
    expect(detectThirdParty(document, true)).toEqual({ confidence: "high", id: "css:ScrollArea", candidates: ["css:ScrollArea"] });
  });

  it("translucent surfaces are not painters", () => {
    surface("ScrollArea", { backgroundColor: "rgba(0, 0, 0, 0.3)" });
    expect(detectThirdParty(document, true)).toEqual({ confidence: "none" });
  });

  it("several painters are ambiguous", () => {
    surface("ScrollArea", { backgroundImage: "linear-gradient(red, blue)" });
    surface("GamepadLibrary", { backgroundColor: "rgb(10, 10, 10)" });
    expect(detectThirdParty(document, true).confidence).toBe("low");
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
