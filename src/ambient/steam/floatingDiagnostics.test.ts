// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import loboSurface from "./fixtures/lobo-keyboard-surface.json";
import terciopeloFocus from "./fixtures/terciopelo-keyboard-focus.json";

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

  it.each(Object.entries(terciopeloFocus.states))("captures Terciopelo's observed %s state without key content", (_, state) => {
    document.documentElement.setAttribute("data-hooandee-keyboard", "terciopelo");
    document.body.innerHTML = '<input value="private draft"><div id="virtual keyboard"><div role="grid"><div data-key-row="private-row" data-key="private-key"><div>private label</div></div></div></div><div class="gpfocus">private conversation</div>';
    const hit = document.querySelector("[data-key-row]")!;
    const face = hit.firstElementChild as HTMLElement;
    const grid = document.querySelector("[role=grid]")!;
    grid.classList.add(terciopeloFocus.classes.Keyboard);
    const other = document.createElement("div");
    other.setAttribute("data-key-row", "private-other-row");
    other.classList.toggle("gpfocus", terciopeloFocus.other_key.gpfocus);
    const otherFace = document.createElement("div");
    otherFace.classList.add(terciopeloFocus.classes.KeyboardKey);
    otherFace.classList.toggle(terciopeloFocus.classes.Focused, terciopeloFocus.other_key.focused.face);
    otherFace.style.borderImageSource = `url("https://steamloopback.host/themes_custom/Hooandee%20Terciopelo/assets/${terciopeloFocus.other_key.sprite}")`;
    other.append(otherFace);
    grid.prepend(other);
    face.classList.add(terciopeloFocus.classes.KeyboardKey);
    hit.classList.toggle(terciopeloFocus.classes.Focused, state.focused.area);
    face.classList.toggle(terciopeloFocus.classes.Focused, state.focused.face);
    hit.classList.toggle("gpfocus", state.gpfocus);
    face.classList.toggle(terciopeloFocus.classes.Touched, state.touched);
    face.style.borderImageSource = `url("https://steamloopback.host/themes_custom/Hooandee%20Terciopelo/assets/${state.sprite}")`;
    const source = {};
    const result = floatingDiagnostics(document, true, source);
    expect(result.keyboard).toHaveProperty("focus", {
      owner_terciopelo: true, focused_count: 2, gpfocus_count: 1, touched_count: state.touched ? 1 : 0,
      face_recognized: true, face_focused: state.sprite.startsWith("velvet-focus"),
      face_pressed: state.sprite.includes("press"),
    });
    expect(result.keyboard).not.toHaveProperty("surface");
    expect(JSON.stringify(result).length).toBeLessThanOrEqual(400);
    expect(JSON.stringify(result)).not.toMatch(/private|https:|velvet-|_21EoN|row|label/);
    hit.classList.add("gpfocus");
    face.classList.add("gpfocus");
    expect(floatingDiagnostics(document, true, source).keyboard).toMatchObject({ focus: { gpfocus_count: 2 } });
    expect(floatingDiagnostics(document, false, source).keyboard).not.toHaveProperty("focus");
    document.documentElement.setAttribute("data-hooandee-keyboard", "private-owner");
    expect(floatingDiagnostics(document, true, source).keyboard).not.toHaveProperty("focus");
  });

  it.each([
    "https://private.example/private-user.png",
    "https://private.example/themes_custom/Hooandee%20Terciopelo/assets/velvet-focus.png",
  ])("keeps an unrecognized or missing face unknown (%s)", (image) => {
    document.documentElement.setAttribute("data-hooandee-keyboard", "terciopelo");
    document.body.innerHTML = '<div id="virtual keyboard"><div role="grid"><div data-key-row="0"><div></div></div></div></div>';
    const face = document.querySelector("[data-key-row] > div") as HTMLElement;
    document.querySelector("[role=grid]")!.classList.add(terciopeloFocus.classes.Keyboard);
    face.classList.add(terciopeloFocus.classes.KeyboardKey, terciopeloFocus.classes.Focused);
    face.parentElement!.classList.add(terciopeloFocus.classes.Focused);
    face.style.borderImageSource = `url("${image}")`;
    const result = floatingDiagnostics(document, true, {});
    expect(result.keyboard).toHaveProperty("focus", {
      owner_terciopelo: true, focused_count: 1, gpfocus_count: 0, touched_count: 0,
      face_recognized: null, face_focused: null, face_pressed: null,
    });
    expect(JSON.stringify(result)).not.toContain("private");
    face.remove();
    expect(floatingDiagnostics(document, true, {}).keyboard).toMatchObject({ focus: { face_recognized: null, face_focused: null, face_pressed: null } });
    document.getElementById("virtual keyboard")!.setAttribute("data-kb-exit", "true");
    expect(floatingDiagnostics(document, true, {}).keyboard).not.toHaveProperty("focus");
  });

  it("does not infer native states or choose the gamepad face on an unknown Steam signature", () => {
    document.documentElement.setAttribute("data-hooandee-keyboard", "terciopelo");
    document.body.innerHTML = '<div id="virtual keyboard"><div role="grid" class="private-new-surface"><div data-key-row="0" class="gpfocus"><div class="private-new-face"></div></div></div></div>';
    const face = document.querySelector("[data-key-row] > div") as HTMLElement;
    face.style.borderImageSource = 'url("https://steamloopback.host/themes_custom/Hooandee%20Terciopelo/assets/velvet-focus.png")';
    const result = floatingDiagnostics(document, true, {});
    expect(result.keyboard).toMatchObject({ focus: {
      owner_terciopelo: true, focused_count: null, gpfocus_count: 1, touched_count: null,
      face_recognized: null, face_focused: null, face_pressed: null,
    } });
    expect(JSON.stringify(result)).not.toMatch(/private|https:|velvet-|gpfocus"/);
    document.querySelector("[role=grid]")!.classList.add(terciopeloFocus.classes.Keyboard);
    face.classList.add(terciopeloFocus.classes.KeyboardKey, terciopeloFocus.classes.Focused);
    expect(floatingDiagnostics(document, true, {}).keyboard).toMatchObject({ focus: {
      focused_count: 1, gpfocus_count: 1, touched_count: 0,
      face_recognized: null, face_focused: null, face_pressed: null,
    } });
  });
});
