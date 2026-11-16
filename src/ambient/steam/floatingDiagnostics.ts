interface KeyboardWindow {
  VirtualKeyboardManager?: { IsShowingVirtualKeyboard?: { Value?: unknown } };
}

interface KeyboardGlobals {
  SteamUIStore?: {
    ActiveWindowInstance?: KeyboardWindow;
    WindowStore?: { MainWindowInstance?: KeyboardWindow; SteamUIWindows?: KeyboardWindow[] };
  };
}

interface KeyboardSurface {
  owner: "lobo-blanco";
  dpr: number | null;
  face: { w: number | null; h: number | null; fractional_x: number | null; fractional_y: number | null };
  border_image: { own: boolean | null; slice: number | null; width: number | null; outset: number | null };
}

interface KeyboardFocus {
  owner_terciopelo: true;
  focused_count: number | null;
  gpfocus_count: number;
  touched_count: number | null;
  face_recognized: true | null;
  face_focused: boolean | null;
  face_pressed: boolean | null;
}

interface FloatingDiagnostics {
  widget: { mounted: boolean | null; visible: boolean | null };
  keyboard: {
    observed: boolean;
    active: boolean | null;
    main: boolean | null;
    windows: number | null;
    observed_windows: number | null;
    showing_windows: number | null;
    surface?: KeyboardSurface;
    focus?: KeyboardFocus;
  };
}

function read<T>(getter: () => T): T | undefined {
  try { return getter(); } catch { return undefined; }
}

function showing(instance?: KeyboardWindow): boolean | null {
  const value = read(() => instance?.VirtualKeyboardManager?.IsShowingVirtualKeyboard?.Value);
  return typeof value === "boolean" ? value : null;
}

function measured(value: number): number | null {
  return Number.isFinite(value) && value >= 0 ? Number(value.toFixed(4)) : null;
}

function cssNumber(value: string, pixels: boolean): number | null {
  const match = value.match(pixels ? /^(\d+(?:\.\d+)?)px$/ : /^(\d+(?:\.\d+)?)(?: fill)?$/);
  return match ? measured(Number(match[1])) : null;
}

function loboSurface(doc: Document | null): KeyboardSurface | undefined {
  try {
    if (doc?.documentElement.getAttribute("data-hooandee-keyboard") !== "lobo-blanco") return;
    const keyboard = doc.getElementById("virtual keyboard");
    if (keyboard?.hasAttribute("data-kb-exit")) return;
    const face = keyboard?.querySelector("[role=grid] [data-key-row] > div");
    const view = doc.defaultView;
    if (!face || !view) return;
    const rect = face.getBoundingClientRect();
    const style = view.getComputedStyle(face);
    const fraction = (value: number) => Number.isFinite(value) ? measured(value - Math.floor(value)) : null;
    return {
      owner: "lobo-blanco",
      dpr: view.devicePixelRatio > 0 ? measured(view.devicePixelRatio) : null,
      face: { w: measured(rect.width), h: measured(rect.height), fractional_x: fraction(rect.x), fractional_y: fraction(rect.y) },
      border_image: {
        own: typeof style.borderImageSource === "string" ? /\/themes_custom\/Hooandee(?:%20| )Lobo(?:%20| )Blanco\/assets\/plush-(?:(?:silver|red|hot)(?:-press)?|maroon)\.png["')]/.test(style.borderImageSource) : null,
        slice: cssNumber(style.borderImageSlice, false),
        width: cssNumber(style.borderImageWidth, true),
        outset: cssNumber(style.borderImageOutset, true),
      },
    };
  } catch { return; }
}

// Native states are available only for allowlisted Steam keyboard signatures.
const KEYBOARD_STATES = [{
  Keyboard: "_45rH7-kY4P2uVEb3TxZhm",
  KeyboardKey: "_2KhPXikozxMpbIRo_6jPxW",
  Focused: "_21EoN2ZlmHNY3fjho_HMae",
  Touched: "_3UFQq1GinEyksceos-TETi",
}] as const;

function terciopeloFace(value: string | undefined, base: string): { focused: boolean; pressed: boolean } | null {
  try {
    const match = value?.match(/^url\(["']?([^"')]+)["']?\)$/);
    if (!match) return null;
    const url = new URL(match[1], base);
    if (!["https:", "http:"].includes(url.protocol) || url.hostname !== "steamloopback.host") return null;
    const sprite = url.pathname.match(/^\/themes_custom\/Hooandee(?:%20| )Terciopelo\/assets\/velvet-(idle|hover|focus|press-v3|focus-press-v3)\.png$/)?.[1];
    return sprite ? { focused: sprite.startsWith("focus"), pressed: sprite.endsWith("press-v3") } : null;
  } catch { return null; }
}

function terciopeloFocus(doc: Document | null): KeyboardFocus | undefined {
  try {
    if (doc?.documentElement.getAttribute("data-hooandee-keyboard") !== "terciopelo") return;
    const keyboard = doc.getElementById("virtual keyboard");
    if (keyboard?.hasAttribute("data-kb-exit")) return;
    const grid = keyboard?.querySelector(":scope > [role=grid]");
    if (!grid) return;
    const keys = [...grid.querySelectorAll("[data-key-row]")];
    const classes = KEYBOARD_STATES.find((state) => grid.classList.contains(state.Keyboard)
      && keys.some((key) => key.firstElementChild?.classList.contains(state.KeyboardKey)));
    const has = (key: Element, token: string) => key.classList.contains(token) || key.firstElementChild?.classList.contains(token) === true;
    const focused = classes ? keys.filter((key) => has(key, classes.Focused)) : null;
    const touched = classes ? keys.filter((key) => has(key, classes.Touched)) : null;
    const gamepad = keys.filter((key) => has(key, "gpfocus"));
    const cursor = classes ? keys.find((key) => key.classList.contains(classes.Focused)
      && key.firstElementChild?.classList.contains(classes.Focused)) : undefined;
    const face = (cursor ?? touched?.[0])?.firstElementChild;
    const image = face ? read(() => doc.defaultView?.getComputedStyle(face).borderImageSource) : undefined;
    const recognized = terciopeloFace(image, doc.baseURI);
    return {
      owner_terciopelo: true,
      focused_count: focused?.length ?? null,
      gpfocus_count: gamepad.length,
      touched_count: touched?.length ?? null,
      face_recognized: recognized ? true : null,
      face_focused: recognized?.focused ?? null,
      face_pressed: recognized?.pressed ?? null,
    };
  } catch { return; }
}

/** Only Panel's card and allowlisted keyboard geometry/state leave this boundary. */
export function floatingDiagnostics(
  doc: Document | null,
  observed: boolean,
  source: unknown = globalThis,
): FloatingDiagnostics {
  const widget: FloatingDiagnostics["widget"] = { mounted: null, visible: null };
  try {
    if (doc) {
      const host = doc.getElementById("pdc-ambient-floating");
      const card = host?.querySelector("[data-pdc-ambient-card]");
      widget.mounted = !!host;
      widget.visible = false;
      if (card) {
        const style = doc.defaultView?.getComputedStyle(card);
        const rect = card.getBoundingClientRect();
        widget.visible = style ? style.display !== "none" && style.visibility !== "hidden"
          && style.opacity !== "0" && rect.width > 0 && rect.height > 0 : null;
      }
    }
  } catch { widget.visible = null; }
  const root = read(() => (source as KeyboardGlobals | null)?.SteamUIStore);
  const store = read(() => root?.WindowStore);
  const windows = read(() => store?.SteamUIWindows);
  const values = Array.isArray(windows) ? windows.map(showing) : null;
  const surface = observed ? loboSurface(doc) : undefined;
  const focus = observed ? terciopeloFocus(doc) : undefined;
  return {
    widget,
    keyboard: {
      observed,
      active: showing(read(() => root?.ActiveWindowInstance)),
      main: showing(read(() => store?.MainWindowInstance)),
      windows: values?.length ?? null,
      observed_windows: values?.filter((value) => value !== null).length ?? null,
      showing_windows: values?.filter((value) => value === true).length ?? null,
      ...(surface ? { surface } : {}),
      ...(focus ? { focus } : {}),
    },
  };
}
