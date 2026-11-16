// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import loboSurface from "./fixtures/lobo-keyboard-surface.json";

import { floatingDiagnostics } from "./floatingDiagnostics";

const captures = [
  { machine: "Ally", showing: false, windows: null, want: { observed: false, active: false, main: false, windows: null, observed_windows: null, showing_windows: null } },
  { machine: "Ally", showing: true, windows: null, want: { observed: true, active: true, main: true, windows: null, observed_windows: null, showing_windows: null } },
  { machine: "Go S", showing: false, windows: 1, want: { observed: false, active: false, main: false, windows: 1, observed_windows: 1, showing_windows: 0 } },
  { machine: "Go S", showing: true, windows: 1, want: { observed: true, active: true, main: true, windows: 1, observed_windows: 1, showing_windows: 1 } },
];

describe("floatingDiagnostics", () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.documentElement.removeAttribute("data-hooandee-keyboard");
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(captures)("captures the observed $machine keyboard state $showing without window content", ({ showing, windows, want }) => {
    const instance = {
      VirtualKeyboardManager: { IsShowingVirtualKeyboard: { Value: showing } },
      BrowserWindow: { document: { body: { textContent: "private conversation" } } },
      m_locationPathname: "/chat/private-account",
    };
    const source = {
      SteamUIStore: {
        ActiveWindowInstance: instance,
        WindowStore: {
          MainWindowInstance: instance,
          ...(windows === null ? {} : { SteamUIWindows: [instance] }),
        },
      },
    };
    expect(floatingDiagnostics(document, showing, source)).toEqual({
      widget: { mounted: false, visible: false },
      keyboard: want,
    });
  });

  it("captures only the recognized Lobo face geometry and nine-slice values from the LCD observation", () => {
    document.documentElement.setAttribute("data-hooandee-keyboard", loboSurface.owner);
    document.body.innerHTML = '<input value="private draft"><div id="virtual keyboard"><div role="grid"><div data-key-row="0" data-key="private character"><div id="own-face"></div></div></div></div>';
    const face = document.getElementById("own-face")!;
    const { rect, style } = loboSurface.face;
    Object.assign(face.style, {
      borderImageSource: `url("https://steamloopback.host/themes_custom/Hooandee%20Lobo%20Blanco/assets/${style.borderImage.split(":")[1]}")`,
      borderImageSlice: style.slice,
      borderImageWidth: style.borderImageWidth,
      borderImageOutset: style.outset,
    });
    vi.spyOn(face, "getBoundingClientRect").mockReturnValue(new DOMRect(rect.x, rect.y, rect.width, rect.height));
    vi.spyOn(document.defaultView!, "devicePixelRatio", "get").mockReturnValue(loboSurface.dpr);
    const result = floatingDiagnostics(document, true, {});
    expect(result.keyboard).toMatchObject({
      surface: {
        owner: "lobo-blanco", dpr: 1.5,
        face: { w: 48.5, h: 44, fractional_x: 0, fractional_y: 0.3125 },
        border_image: { own: true, slice: 54, width: 18, outset: 6 },
      },
    });
    expect(JSON.stringify(result).length).toBeLessThanOrEqual(400);
    expect(JSON.stringify(result)).not.toMatch(/private|https:|plush-silver/);
    expect(floatingDiagnostics(document, false, {}).keyboard).not.toHaveProperty("surface");
    document.documentElement.setAttribute("data-hooandee-keyboard", "unrecognized-theme");
    expect(floatingDiagnostics(document, true, {}).keyboard).not.toHaveProperty("surface");
  });

  it("uses null for invalid measurements and never records an unfamiliar image URL", () => {
    document.documentElement.setAttribute("data-hooandee-keyboard", loboSurface.owner);
    document.body.innerHTML = '<div id="virtual keyboard"><div role="grid"><div data-key-row="0"><div id="own-face"></div></div></div></div>';
    const face = document.getElementById("own-face")!;
    vi.spyOn(face, "getBoundingClientRect").mockReturnValue(new DOMRect(NaN, Infinity, Infinity, -1));
    vi.spyOn(document.defaultView!, "devicePixelRatio", "get").mockReturnValue(NaN);
    vi.spyOn(document.defaultView!, "getComputedStyle").mockReturnValue({
      borderImageSource: 'url("https://private.example/private-user.png")',
      borderImageSlice: "54% fill", borderImageWidth: "auto", borderImageOutset: "var(--private)",
    } as CSSStyleDeclaration);
    const result = floatingDiagnostics(document, true, {});
    expect(result.keyboard).toMatchObject({
      surface: {
        owner: "lobo-blanco", dpr: null,
        face: { w: null, h: null, fractional_x: null, fractional_y: null },
        border_image: { own: false, slice: null, width: null, outset: null },
      },
    });
    expect(JSON.stringify(result)).not.toContain("private");
  });

  it("reports an unavailable source as unknown while retaining the observed subscription value", () => {
    const source = { get SteamUIStore(): never { throw new Error("window unavailable"); } };
    expect(floatingDiagnostics(null, true, source)).toEqual({
      widget: { mounted: null, visible: null },
      keyboard: { observed: true, active: null, main: null, windows: null, observed_windows: null, showing_windows: null },
    });
  });
});
