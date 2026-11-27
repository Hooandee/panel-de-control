// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const hoisted = vi.hoisted(() => ({
  overview: vi.fn(),
  listeners: new Set<(update: { job: { appid: string }; finished: boolean }) => void>(),
}));
vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: { addGlobalComponent: () => {}, removeGlobalComponent: () => {} }, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), getUpscalersOverview: hoisted.overview }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, args?: { provider?: string }) =>
  key === "up.overlay.active" ? `${args?.provider} active` : key }) }));
vi.mock("../platform/overGameComposition", () => ({ OverGameComposition: () => null }));
vi.mock("../platform/qamSurface", () => ({ subscribeQamSurface: () => () => {} }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => ({ liveAppid: 3564860 }) }));
vi.mock("./gameInFront", () => ({ useGameInFront: () => true }));
vi.mock("./fpsCounter", () => ({ startFpsCounterSession: () => () => {} }));
vi.mock("./useOverlayLive", () => ({ useOverlayLive: () => ({ live: { result: "active", provider_family: "fsr", provider_name: "FSR", provider_version: null, provider_source: "optiscaler_log", provider_confidence: "family_only" }, lossless: null, makoSpatial: null, makoMultiplier: null, makoResolutionWarning: false }) }));
vi.mock("./jobRunner", () => ({
  onJobUpdate: (listener: (update: { job: { appid: string }; finished: boolean }) => void) => {
    hoisted.listeners.add(listener);
    return () => { hoisted.listeners.delete(listener); };
  },
}));
import { InGameBadge, startUpscalerOverlays, writeInGameMode } from "./overlays";

const builds = [
  { id: "fsr-4.1.2-beta", engine: "optiscaler", family: "fsr", version: "4.1.2", models: ["lite", "full"] },
  { id: "hlx-fsr4", engine: "helixsr", family: "helixsr", version: "3.3.0" },
];
const overview = (build: string) => ({ builds, installs: { "3564860": { build, status: "installed", options: { model: "lite" } } } });

beforeEach(() => { writeInGameMode("always"); hoisted.listeners.clear(); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("names the HelixSR install in the pill once its job finishes, not the OptiScaler one it replaced", async () => {
  hoisted.overview.mockResolvedValueOnce(overview("fsr-4.1.2-beta")).mockResolvedValue(overview("hlx-fsr4"));
  const stop = startUpscalerOverlays();
  render(<InGameBadge />);
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByText("FSR active")).toBeTruthy();
  await act(async () => { for (const listener of hoisted.listeners) listener({ job: { appid: "3564860" }, finished: true }); });
  expect(screen.queryByText("FSR active")).toBeNull();
  expect(screen.getByText(/^HLX 3\.3\.0/)).toBeTruthy();
  stop();
});
