import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getHudState: vi.fn(),
  visible: vi.fn(async () => ({})),
  hidden: vi.fn(async () => ({})),
}));

vi.mock("../api", () => ({ getHudState: mocks.getHudState }));
vi.mock("./steamOverlay", () => ({
  steamOverlay: {
    ensureFullHudVisible: mocks.visible,
    ensureHudHidden: mocks.hidden,
  },
}));

import { noteHudScope, resetHudGameSyncForTest, syncSteamOverlayForGame } from "./hudGameSync";

const hud = (enabled: boolean, followsGlobal: boolean) => ({
  model: { enabled },
  followsGlobal,
});

describe("syncSteamOverlayForGame", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetHudGameSyncForTest();
  });

  it("never touches Steam's level for a user who has no game HUD", async () => {
    mocks.getHudState.mockResolvedValue(hud(false, true));
    await syncSteamOverlayForGame();
    mocks.getHudState.mockResolvedValue(hud(true, true));
    await syncSteamOverlayForGame();
    expect(mocks.visible).not.toHaveBeenCalled();
    expect(mocks.hidden).not.toHaveBeenCalled();
  });

  it("entering a game with its own HUD on shows it, leaving restores the global off", async () => {
    mocks.getHudState.mockResolvedValue(hud(true, false));
    await syncSteamOverlayForGame();
    expect(mocks.visible).toHaveBeenCalledTimes(1);

    mocks.getHudState.mockResolvedValue(hud(false, true));
    await syncSteamOverlayForGame();
    expect(mocks.hidden).toHaveBeenCalledTimes(1);

    mocks.getHudState.mockResolvedValue(hud(false, true));
    await syncSteamOverlayForGame();
    expect(mocks.hidden).toHaveBeenCalledTimes(1);
  });

  it("a game with its own HUD off hides it while global stays on afterwards", async () => {
    mocks.getHudState.mockResolvedValue(hud(false, false));
    await syncSteamOverlayForGame();
    expect(mocks.hidden).toHaveBeenCalledTimes(1);

    mocks.getHudState.mockResolvedValue(hud(true, true));
    await syncSteamOverlayForGame();
    expect(mocks.visible).toHaveBeenCalledTimes(1);
  });

  it("a game that follows global does not change anything after leaving a non-engaged state", async () => {
    mocks.getHudState.mockResolvedValue(hud(true, true));
    await syncSteamOverlayForGame();
    expect(mocks.visible).not.toHaveBeenCalled();
  });

  it("restores global after the UI created a game HUD this session", async () => {
    noteHudScope(true);
    mocks.getHudState.mockResolvedValue(hud(true, true));
    await syncSteamOverlayForGame();
    expect(mocks.visible).toHaveBeenCalledTimes(1);
  });
});
