import { afterEach, describe, expect, it, vi } from "vitest";

import { installSteamButtonHome } from "./steamButton";

type Activated = (pid: number, appId: number, active: boolean, user: boolean) => void;

function steam() {
  const calls: string[] = [];
  let activated: Activated | undefined;
  let requested: (() => void) | undefined;
  let historyListener: ((location: { pathname?: string }) => void) | undefined;
  const overlayPrototype = { OnHomeButtonPressed() { calls.push("steam overlay menu"); } };
  const overlay = Object.assign(Object.create(overlayPrototype), { MainRunningAppID: 2514320289 });
  const scope = {
    SteamClient: {
      Overlay: {
        RegisterForOverlayActivated: (callback: Activated) => { activated = callback; return { unregister: () => calls.push("unregistered") }; },
        RegisterForActivateOverlayRequests: (callback: () => void) => { requested = callback; return { unregister() {} }; },
        SetOverlayState: (gameId: string, mode: number) => calls.push(`overlay ${gameId} ${mode}`),
      },
      Apps: { RaiseWindowForGame: (gameId: string) => { calls.push(`raise ${gameId}`); return Promise.resolve(2); } },
    },
    SteamUIStore: {
      RunningApps: [{ appid: 2514320289, m_gameid: "10798923412957822976" }],
      WindowStore: {
        GamepadUIMainWindowInstance: {
          MainRunningAppID: 2514320289,
          GetFocusNavContext: () => ({ SetActive: (active: boolean) => calls.push(`context ${active}`) }),
          Navigator: { Home: () => calls.push("home") },
          BrowserWindow: { SteamClient: { Window: { BringToFront: () => calls.push("front") } } },
          m_history: { listen: (listener: (location: { pathname?: string }) => void) => { historyListener = listener; return () => calls.push("unlisten"); } },
        },
        m_mapOverlayPopupByPID: new Map([[19984, overlay]]),
      },
    },
  };
  return {
    scope: scope as unknown as typeof globalThis,
    calls,
    overlay,
    activate: (active: boolean, user = true) => activated?.(19984, 2514320289, active, user),
    gameRequest: () => requested?.(),
    navigate: (pathname: string) => historyListener?.({ pathname }),
  };
}

const errors: string[] = [];
const log = (code: string) => { errors.push(code); };

afterEach(() => {
  errors.length = 0;
  vi.useRealTimers();
});

describe("Steam button on Windows", () => {
  it("goes back to Big Picture's Home over the game, keeping the controller on Steam's UI", () => {
    vi.useFakeTimers();
    const { scope, calls, overlay } = steam();
    const stop = installSteamButtonHome(scope, () => true, log);

    overlay.OnHomeButtonPressed();
    vi.advanceTimersByTime(500);

    expect(calls).toEqual(["overlay 10798923412957822976 2", "home", "front", "context true", "context true", "context true"]);
    stop();
    calls.length = 0;
    overlay.OnHomeButtonPressed();
    expect(calls).toEqual(["steam overlay menu"]);
  });

  it("takes Big Picture back when the player opens the overlay another way, but not when the game asks for it", () => {
    const { scope, calls, activate, gameRequest } = steam();
    const stop = installSteamButtonHome(scope, () => true, log);

    activate(true);
    expect(calls.slice(0, 3)).toEqual(["overlay 10798923412957822976 2", "home", "front"]);

    calls.length = 0;
    activate(false, false);
    gameRequest();
    activate(true);
    expect(calls).toEqual([]);
    stop();
  });

  it("raises the game when Big Picture resumes it", () => {
    const { scope, calls, navigate } = steam();
    const stop = installSteamButtonHome(scope, () => true, log);

    navigate("/library/home");
    navigate("/apprunning");

    expect(calls).toEqual(["overlay 10798923412957822976 0", "raise 10798923412957822976"]);
    stop();
    expect(errors).toEqual([]);
  });

  it("leaves Steam alone while no theme runtime is mounted", () => {
    const { scope, calls, overlay, activate, navigate } = steam();
    const stop = installSteamButtonHome(scope, () => false, log);

    overlay.OnHomeButtonPressed();
    activate(true);
    navigate("/apprunning");

    expect(calls).toEqual(["steam overlay menu"]);
    stop();
  });
});
