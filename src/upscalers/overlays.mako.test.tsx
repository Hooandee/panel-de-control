// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: {}, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../platform/overGameComposition", () => ({ OverGameComposition: () => null }));
vi.mock("../platform/qamSurface", () => ({ subscribeQamSurface: () => () => {} }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => ({ liveAppid: 1462040 }) }));
vi.mock("./gameInFront", () => ({ useGameInFront: () => true }));
vi.mock("./useOverlayLive", () => ({ useOverlayLive: vi.fn() }));
import { useOverlayLive } from "./useOverlayLive";
import { InGameBadge, publishOverview, writeInGameMode } from "./overlays";

beforeEach(() => {
  publishOverview({ builds: [], installs: {} } as never);
  writeInGameMode("always");
  vi.mocked(useOverlayLive).mockReturnValue({ live: null, lossless: null, makoName: "Mako 5", makoSpatial: null, makoMultiplier: null, makoResolutionWarning: true });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("renders the warning without an OptiScaler badge and removes it when resolved", () => {
  const { rerender } = render(<InGameBadge />);
  const warning = screen.getByText("up.overlay.makoResolution");
  expect(warning.parentElement?.style.opacity).toBe("0.92");
  vi.mocked(useOverlayLive).mockReturnValue({ live: null, lossless: null, makoName: "Mako 5", makoSpatial: null, makoMultiplier: null, makoResolutionWarning: false });
  rerender(<InGameBadge />);
  expect(screen.queryByText("up.overlay.makoResolution")).toBeNull();
});
it("respects the disabled in-game pill setting", () => {
  writeInGameMode("off");
  render(<InGameBadge />);
  expect(screen.getByText("up.overlay.makoResolution").parentElement?.style.opacity).toBe("0");
});

it("shows confirmed Mako generation without an OptiScaler install", () => {
  vi.mocked(useOverlayLive).mockReturnValue({ live: null, lossless: null, makoName: "Mako 5", makoSpatial: null, makoResolutionWarning: false, makoMultiplier: 2 });
  const { rerender } = render(<InGameBadge />);
  expect(screen.getByText("Mako 5 ×2").parentElement?.textContent).toContain("up.overlay.generating");
  expect(screen.getByText("Mako 5 ×2").parentElement?.parentElement?.style.opacity).toBe("0.92");
  vi.mocked(useOverlayLive).mockReturnValue({ live: null, lossless: null, makoName: "Mako 5", makoSpatial: null, makoResolutionWarning: false, makoMultiplier: null });
  rerender(<InGameBadge />);
  expect(screen.queryByText("Mako 5 ×2")).toBeNull();
});
it.each([true, false])("shows the observed family when the log only proves a family (build listed: %s)", (listed) => {
  publishOverview({ builds: listed ? [{ id: "fsr-4.1.1", family: "fsr", version: "4.1.1", engine: "optiscaler" }] : [],
    installs: { "1462040": { build: "fsr-4.1.1", status: "active", options: {} } } } as never);
  vi.mocked(useOverlayLive).mockReturnValue({ live: { result: "active", resolution: { render: [960, 540], output: [1920, 1080] }, provider_name: "FSR", provider_version: null, provider_source: "optiscaler_log", provider_confidence: "family_only" }, lossless: null, makoName: "Mako 5", makoSpatial: null, makoResolutionWarning: false, makoMultiplier: null });
  render(<InGameBadge />);
  expect(screen.getByText("FSR").parentElement?.textContent).toContain("540p → 1080p");
  expect(screen.queryByText("FSR 4.1.1")).toBeNull();
  expect(screen.queryByText("up.overlay.configured")).toBeNull();
});

it("shows the confirmed provider version and model when they differ from the package", () => {
  publishOverview({ builds: [{ id: "fsr-4.1.1", family: "fsr", version: "4.1.1", engine: "optiscaler" }],
    installs: { "1462040": { build: "fsr-4.1.1", status: "active", options: {} } } } as never);
  const state = { makoName: "Mako 5", live: { result: "active", provider_name: "FSR" as const, provider_version: "4.1.2", provider_model: "INT8", provider_source: "optiscaler_log" as const, provider_confidence: "log_provider" as const }, lossless: null, makoSpatial: null, makoResolutionWarning: false, makoMultiplier: null };
  vi.mocked(useOverlayLive).mockReturnValue(state);
  const { rerender } = render(<InGameBadge />);
  expect(screen.getByText("FSR 4.1.2 INT8")).toBeTruthy();
  expect(screen.queryByText("up.overlay.configured")).toBeNull();
  vi.mocked(useOverlayLive).mockReturnValue({ ...state, live: { ...state.live, provider_source: "unavailable" } });
  rerender(<InGameBadge />);
  expect(screen.getByText("FSR 4.1.1")).toBeTruthy();
  expect(screen.queryByText("up.overlay.configured")).toBeNull();
  vi.mocked(useOverlayLive).mockReturnValue({ ...state, live: { ...state.live,
    fallback: { requested: "FSR 4", observed: "FSR 3.1", reason: "backend_changed" } } });
  rerender(<InGameBadge />);
  expect(screen.getByText("up.fallback.line")).toBeTruthy();
  expect(screen.queryByText("FSR 4.1.2 INT8")).toBeNull();
});
it("keeps Lossless configuration separate from confirmed Mako generation", () => {
  vi.mocked(useOverlayLive).mockReturnValue({ makoName: "Mako 5", live: null, makoSpatial: null, lossless: { name: "Game", multiplier: 2, flow_scale: 0.75, performance: true }, makoResolutionWarning: false, makoMultiplier: 2 });
  render(<InGameBadge />);
  expect(screen.getByText("Lossless Scaling ×2 · up.lsfg.flowScale 75 %").parentElement?.textContent).toContain("up.overlay.configured");
  expect(screen.getByText("Mako 5 ×2").parentElement?.textContent).toContain("up.overlay.generating");
});
it("shows observed spatial dimensions without any installed badge or frame generation", () => {
  vi.mocked(useOverlayLive).mockReturnValue({ makoName: "Mako 5", live: null, lossless: null, makoMultiplier: null,
    makoResolutionWarning: false, makoSpatial: { render: [1280, 720], output: [1920, 1080] } });
  const { rerender } = render(<InGameBadge />);
  expect(screen.getByText("1280×720 → 1920×1080").parentElement?.textContent).toBe("Mako 51280×720 → 1920×1080");
  expect(screen.getByText("Mako 5").parentElement?.parentElement?.style.opacity).toBe("0.92");
  expect(screen.queryByText("up.overlay.generating")).toBeNull();
  vi.mocked(useOverlayLive).mockReturnValue({ makoName: "Mako 5", live: null, lossless: null, makoMultiplier: null,
    makoResolutionWarning: false, makoSpatial: null });
  rerender(<InGameBadge />);
  expect(screen.queryByText("1280×720 → 1920×1080")).toBeNull();
});
it.each([
  ["xess", undefined, "XeSS"],
  ["dlss", "DLSS", "DLSS"],
])("names the provider the log observes when it is not the installed one (%s)", (family, name, shown) => {
  publishOverview({ builds: [{ id: "fsr-build", family: "fsr", version: "4.1.2", engine: "optiscaler" }],
    installs: { "1462040": { build: "fsr-build", status: "active", options: {} } } } as never);
  vi.mocked(useOverlayLive).mockReturnValue({ live: { result: "active", provider_family: family as "xess" | "dlss", provider_name: name as "DLSS" | undefined, provider_version: null, provider_source: "optiscaler_log" }, lossless: null, makoName: "Mako 5", makoSpatial: null, makoResolutionWarning: false, makoMultiplier: null });
  render(<InGameBadge />);
  expect(screen.getByText(shown)).toBeTruthy();
  expect(screen.queryByText("FSR 4.1.2")).toBeNull();
});
it("does not present an unloaded scaler as working beside an active Lossless", () => {
  publishOverview({ builds: [{ id: "fsr-build", family: "fsr", version: "4.1.2", engine: "optiscaler" }],
    installs: { "1462040": { build: "fsr-build", status: "active", options: {} } } } as never);
  vi.mocked(useOverlayLive).mockReturnValue({ makoName: "Mako 5", live: null, lossless: { name: "Game", multiplier: 2, flow_scale: 0.75, performance: true }, makoSpatial: null, makoResolutionWarning: false, makoMultiplier: null });
  render(<InGameBadge />);
  expect(screen.getByText("Lossless Scaling ×2 · up.lsfg.flowScale 75 %")).toBeTruthy();
  expect(screen.queryByText("FSR 4.1.2")).toBeNull();
});
