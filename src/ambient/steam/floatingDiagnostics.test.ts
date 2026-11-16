// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { floatingDiagnostics } from "./floatingDiagnostics";

const captures = [
  { machine: "Ally", showing: false, windows: null, want: { observed: false, active: false, main: false, windows: null, observed_windows: null, showing_windows: null } },
  { machine: "Ally", showing: true, windows: null, want: { observed: true, active: true, main: true, windows: null, observed_windows: null, showing_windows: null } },
  { machine: "Go S", showing: false, windows: 1, want: { observed: false, active: false, main: false, windows: 1, observed_windows: 1, showing_windows: 0 } },
  { machine: "Go S", showing: true, windows: 1, want: { observed: true, active: true, main: true, windows: 1, observed_windows: 1, showing_windows: 1 } },
];

describe("floatingDiagnostics", () => {
  afterEach(() => { document.body.replaceChildren(); });

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

  it("reports an unavailable source as unknown while retaining the observed subscription value", () => {
    const source = { get SteamUIStore(): never { throw new Error("window unavailable"); } };
    expect(floatingDiagnostics(null, true, source)).toEqual({
      widget: { mounted: null, visible: null },
      keyboard: { observed: true, active: null, main: null, windows: null, observed_windows: null, showing_windows: null },
    });
  });
});
