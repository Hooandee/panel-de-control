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

/** Only Panel's card and the known keyboard's numeric geometry leave this boundary. */
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
    },
  };
}
