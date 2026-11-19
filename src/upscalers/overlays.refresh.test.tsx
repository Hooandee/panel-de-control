// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const hoisted = vi.hoisted(() => ({
  overview: vi.fn(),
  prefs: vi.fn(),
  listeners: new Set<(update: { job: { appid: string }; finished: boolean }) => void>(),
}));
vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: { addGlobalComponent: () => {}, removeGlobalComponent: () => {} }, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), getUpscalersOverview: hoisted.overview, getUiPrefs: hoisted.prefs }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
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
import { hydratePrefs } from "../system/pdcStorage";
import { InGameBadge, refreshUpscalersOverview, startUpscalerOverlays, upscalerCoverLabels, writeCoverBadges, writeInGameMode } from "./overlays";

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
  expect(screen.getByText("FSR 4.1.2 Lite")).toBeTruthy();
  await act(async () => { for (const listener of hoisted.listeners) listener({ job: { appid: "3564860" }, finished: true }); });
  expect(screen.queryByText("FSR 4.1.2 Lite")).toBeNull();
  expect(screen.getByText(/^HLX 3\.3\.0/)).toBeTruthy();
  stop();
});

it("feeds theme covers from startup and finished jobs and honors the restored cover setting", async () => {
  const appid = "3564860";
  const shortcutId = "12283760549434720256";
  const engineOnly = { [shortcutId]: { lossless: { multiplier: 2 } } };
  hoisted.overview
    .mockResolvedValueOnce({ ...overview("fsr-4.1.2-beta"), engines: engineOnly })
    .mockResolvedValueOnce({ builds, installs: {}, engines: engineOnly });
  hoisted.prefs.mockResolvedValue({ "pdc:upscalers:covers": "off" });

  const stop = startUpscalerOverlays();
  const seen = vi.fn(() => upscalerCoverLabels.read());
  const off = upscalerCoverLabels.subscribe(seen);
  try {
    await vi.waitFor(() => expect(seen).toHaveReturnedWith({
      [appid]: { label: "FSR 4.1.2 Lite", short: "FSR 4 Lite", state: "installed" },
      [shortcutId]: { label: "Lossless ×2", short: "Lossless ×2", state: "pending" },
    }));
    const before = upscalerCoverLabels.read();
    expect(Object.isFrozen(before)).toBe(true);
    expect(Object.isFrozen(before[appid])).toBe(true);

    await hydratePrefs();
    expect(seen).toHaveLastReturnedWith({});

    for (const listener of hoisted.listeners) listener({ job: { appid }, finished: true });
    await vi.waitFor(() => expect(hoisted.overview).toHaveBeenCalledTimes(2));
    expect(upscalerCoverLabels.read()).toEqual({});

    writeCoverBadges(true);
    expect(seen).toHaveLastReturnedWith({
      [shortcutId]: { label: "Lossless ×2", short: "Lossless ×2", state: "pending" },
    });
    expect(before[appid].short).toBe("FSR 4 Lite");

    const count = seen.mock.calls.length;
    off();
    writeCoverBadges(false);
    expect(upscalerCoverLabels.read()).toEqual({});
    expect(seen).toHaveBeenCalledTimes(count);
  } finally {
    off();
    stop();
  }
});

it("keeps the finished job's cover labels when the slower startup overview arrives", async () => {
  let resolveStartup!: (data: ReturnType<typeof overview>) => void;
  hoisted.overview
    .mockReturnValueOnce(new Promise((resolve) => { resolveStartup = resolve; }))
    .mockResolvedValueOnce(overview("hlx-fsr4"));
  writeCoverBadges(true);

  const stop = startUpscalerOverlays();
  try {
    await act(async () => {
      for (const listener of hoisted.listeners) listener({ job: { appid: "3564860" }, finished: true });
    });
    expect(upscalerCoverLabels.read()["3564860"].short).toBe("HLX 3");

    await act(async () => { resolveStartup(overview("fsr-4.1.2-beta")); });
    expect(upscalerCoverLabels.read()["3564860"].short).toBe("HLX 3");
  } finally {
    stop();
  }
});

it("still publishes the startup overview if a newer request fails", async () => {
  let resolveStartup!: (data: ReturnType<typeof overview>) => void;
  hoisted.overview
    .mockReturnValueOnce(new Promise((resolve) => { resolveStartup = resolve; }))
    .mockRejectedValueOnce(new Error("backend unavailable"));

  const stop = startUpscalerOverlays();
  try {
    await expect(refreshUpscalersOverview()).rejects.toThrow("backend unavailable");
    await act(async () => { resolveStartup(overview("fsr-4.1.2-beta")); });
    expect(upscalerCoverLabels.read()["3564860"].short).toBe("FSR 4 Lite");
  } finally {
    stop();
  }
});
