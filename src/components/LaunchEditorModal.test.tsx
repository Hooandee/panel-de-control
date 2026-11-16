// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GameEntry } from "../launch/steamApi";

const mocks = vi.hoisted(() => ({
  modal: null as ReactNode,
  write: vi.fn(() => true),
  saveLibrary: vi.fn(),
  loadLibrary: vi.fn(async () => [{ id: "reported-variable", name: "Hide Shader Compilation", kind: "env", envName: "DXVK_HUD", envValue: "0" }]),
}));

vi.mock("@decky/ui", () => ({
  ModalRoot: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  showModal: (node: ReactNode) => { mocks.modal = node; },
  Spinner: () => <span>Loading</span>,
  TextField: (props: object) => <input {...props} />,
  Focusable: ({ children, onActivate, onClick, onGamepadFocus: _focus, onGamepadBlur: _blur, ...props }: {
    children?: ReactNode; onActivate?: () => void; onClick?: () => void;
    onGamepadFocus?: () => void; onGamepadBlur?: () => void; [key: string]: unknown;
  }) => createElement(onActivate || onClick ? "button" : "div", {
    ...props, onClick: onClick ?? onActivate,
    ...(onActivate || onClick ? { type: "button" } : {}),
  }, children),
}));
vi.mock("@decky/api", () => ({ toaster: { toast: vi.fn() } }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }), translate: (key: string) => key }));
vi.mock("../api", () => ({
  getCustomLaunchVars: mocks.loadLibrary,
  setCustomLaunchVars: mocks.saveLibrary,
  getLaunchTools: async () => ({ lsfg: true, mangohud: true, gamemode: false, gamescope: true, distro: "steamos", locale_reliable: false }),
  getDevice: async () => ({ gpu_gen: "unknown" }),
  getProtonCaps: async () => ({ found: false, envs: [] }),
  getLaunchUsage: async () => ({ langEs: 3, "custom:reported-variable": 2, lsfg: 1, noVideo: 1 }),
  bumpLaunchUsage: vi.fn(),
}));
vi.mock("../launch/steamApi", () => ({
  readAppDetails: async () => ({ launch: "", compatName: "", compatDisplay: "" }),
  writeLaunchOptions: mocks.write,
}));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => null }));
vi.mock("../launch/useHiddenGames", () => ({ useHiddenGames: () => ({ isHidden: () => false }) }));
vi.mock("./RemovableRow", () => ({ RemovableRow: ({ children }: { children: ReactNode }) => <div>{children}</div> }));

import { openLaunchEditorModal } from "./LaunchEditorModal";
import { openCustomVarsManager } from "./CustomVarsManager";
import { setUiEventSink, type UiEventSink } from "../system/uiEvents";

const game: GameEntry = {
  liveAppid: 1, stableKey: "ns:reported-game", instanceKey: "1", name: "Reported game",
  isNonSteam: true, coverUrls: [], lastPlayed: 0, playtime: 0,
};

afterEach(() => { cleanup(); setUiEventSink(null); vi.clearAllMocks(); });

describe("custom launch variables", () => {
  it("shows the reported DXVK_HUD=0 variable in the manager and in Advanced without writing the game", async () => {
    const events: Array<{ area: string; action: string; fields: unknown; ok: boolean }> = [];
    const sink: UiEventSink = (area, action, detail, ok) => { events.push({ area, action, fields: JSON.parse(detail), ok }); };
    setUiEventSink(sink);
    openCustomVarsManager(() => {});
    render(mocks.modal);
    await screen.findByText("Hide Shader Compilation");
    expect(screen.getByText("DXVK_HUD=0")).toBeTruthy();
    cleanup();

    openLaunchEditorModal(game, () => {});
    render(mocks.modal);
    const advanced = await screen.findByText("params.advanced");
    expect(screen.queryByRole("switch", { name: "Hide Shader Compilation" })).toBeNull();
    await waitFor(() => {
      setUiEventSink(sink);
      expect(events).toContainEqual({ area: "launch", action: "editor_state", fields: { state: "ready", custom_state: "ready", custom_count: 1, advanced_open: false }, ok: true });
    });
    fireEvent.click(advanced);
    expect(screen.getByRole("switch", { name: "Hide Shader Compilation" }).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("DXVK_HUD=0")).toBeTruthy();
    setUiEventSink(null);
    expect(events[events.length - 1]).toEqual({ area: "launch", action: "editor_state", fields: { state: "ready", custom_state: "ready", custom_count: 1, advanced_open: true }, ok: true });
    expect(JSON.stringify(events)).not.toMatch(/Hide Shader Compilation|DXVK_HUD|reported-variable|Reported game|reported-game/);
    cleanup();
    expect(mocks.write).not.toHaveBeenCalled();
    expect(mocks.saveLibrary).not.toHaveBeenCalled();
  });

  it("records an unread custom library as unknown rather than an empty library", async () => {
    mocks.loadLibrary.mockRejectedValueOnce(new Error("private library error DXVK_HUD=0"));
    const events: Array<{ fields: unknown; ok: boolean }> = [];
    const sink: UiEventSink = (_area, _action, detail, ok) => { events.push({ fields: JSON.parse(detail), ok }); };
    setUiEventSink(sink);
    openLaunchEditorModal(game, () => {});
    render(mocks.modal);
    await screen.findByText("params.advanced");
    await waitFor(() => {
      setUiEventSink(sink);
      expect(events[events.length - 1]).toEqual({ fields: { state: "ready", custom_state: "error", custom_count: null, advanced_open: false }, ok: false });
    });
    setUiEventSink(null);
    expect(JSON.stringify(events)).not.toContain("private library error");
    expect(screen.queryByRole("switch", { name: "Hide Shader Compilation" })).toBeNull();
    cleanup();
    expect(mocks.write).not.toHaveBeenCalled();
    expect(mocks.saveLibrary).not.toHaveBeenCalled();
  });
});
