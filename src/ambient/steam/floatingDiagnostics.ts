interface KeyboardWindow {
  VirtualKeyboardManager?: { IsShowingVirtualKeyboard?: { Value?: unknown } };
}

interface KeyboardGlobals {
  SteamUIStore?: {
    ActiveWindowInstance?: KeyboardWindow;
    WindowStore?: { MainWindowInstance?: KeyboardWindow; SteamUIWindows?: KeyboardWindow[] };
  };
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
  };
}

function read<T>(getter: () => T): T | undefined {
  try { return getter(); } catch { return undefined; }
}

function showing(instance?: KeyboardWindow): boolean | null {
  const value = read(() => instance?.VirtualKeyboardManager?.IsShowingVirtualKeyboard?.Value);
  return typeof value === "boolean" ? value : null;
}

/** Only Panel's card and boolean/count keyboard state leave this boundary. */
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
  return {
    widget,
    keyboard: {
      observed,
      active: showing(read(() => root?.ActiveWindowInstance)),
      main: showing(read(() => store?.MainWindowInstance)),
      windows: values?.length ?? null,
      observed_windows: values?.filter((value) => value !== null).length ?? null,
      showing_windows: values?.filter((value) => value === true).length ?? null,
    },
  };
}
