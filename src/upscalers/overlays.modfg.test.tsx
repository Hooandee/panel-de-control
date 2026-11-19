// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: {}, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../platform/overGameComposition", () => ({ OverGameComposition: () => null }));
vi.mock("../platform/qamSurface", () => ({ subscribeQamSurface: () => () => {} }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => ({ liveAppid: 1245620 }) }));
vi.mock("./gameInFront", () => ({ useGameInFront: () => true }));
vi.mock("./useOverlayLive", () => ({ useOverlayLive: vi.fn() }));
import { useOverlayLive } from "./useOverlayLive";
import { InGameBadge, publishOverview, writeInGameMode } from "./overlays";

beforeEach(() => {
  vi.mocked(useOverlayLive).mockReturnValue({ live: { fg: null } as never, lossless: null, makoName: "Mako 5", makoSpatial: null, makoMultiplier: null, makoResolutionWarning: false });
  publishOverview({ builds: [{ id: "fsr-4.1.2-beta", engine: "optiscaler", family: "fsr", version: "4.1.2" }],
    installs: { "1245620": { build: "fsr-4.1.2-beta", status: "active", options: {}, mod_fg: "ERSS-FG" } } } as never);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("names the frame generation the mod runs and hides it like the other pills", () => {
  writeInGameMode("always");
  render(<InGameBadge />);
  const pill = screen.getByText("ERSS-FG");
  expect(pill.nextElementSibling?.textContent).toBe("up.overlay.configured");
  expect(pill.parentElement?.parentElement?.style.opacity).toBe("0.92");
  act(() => writeInGameMode("off"));
  expect(screen.getByText("ERSS-FG").parentElement?.parentElement?.style.opacity).toBe("0");
});
