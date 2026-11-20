// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const games = vi.hoisted(() => [
  { installed: true, liveAppid: 1, instanceKey: "1", name: "A", coverUrls: [], lastPlayed: 2, isNonSteam: false },
  { installed: true, liveAppid: 2, instanceKey: "2", name: "B", coverUrls: [], lastPlayed: 1, isNonSteam: false },
]);
vi.mock("@decky/ui", () => ({ Focusable: ({ children }: any) => <div>{children}</div> }));
vi.mock("../api", () => ({
  getUpscalersOverview: vi.fn(async () => ({ builds: [], installs: {}, job: null, preferred: "fsr" })),
  getUpscalersCompat: vi.fn(async () => ({})),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/FocusableCard", () => ({ FocusableCard: ({ children }: any) => <div>{children}</div> }));
vi.mock("../components/GameCover", () => ({ GameCover: () => null }));
vi.mock("../upscalers/BulkPanel", () => ({ BulkPanel: () => null }));
vi.mock("../upscalers/overlays", () => ({
  IN_GAME_MODES: [], publishOverview: vi.fn(), readInGameMode: () => "start", setUpscalersSectionOpen: vi.fn(), writeInGameMode: vi.fn(), readCoverBadges: () => true, writeCoverBadges: vi.fn(),
}));
vi.mock("../upscalers/pageMemory", () => ({ showGame: vi.fn(), takeHeldPage: () => null }));
vi.mock("../upscalers/GameView", () => ({
  GameView: ({ game }: { game: { liveAppid: number } }) => {
    const [firstAppid] = useState(game.liveAppid);
    return <output data-testid="page">{`${firstAppid}:${game.liveAppid}`}</output>;
  },
}));

import { openUpscalersFor } from "../upscalers/deepLink";
import { readSelectorContext } from "../upscalers/selectorContext";
import { EscaladoresSection } from "./EscaladoresSection";

vi.mock("../deckyInternal", () => ({ setActivePlugin: vi.fn() }));
vi.mock("./activeTab", () => ({ writeActiveTab: vi.fn() }));
vi.mock("./shellMode", () => ({ setShellMode: vi.fn() }));

beforeEach(() => {
  vi.stubGlobal("collectionStore", { allAppsCollection: {
    get allApps() {
      return games.map((game) => ({ appid: game.liveAppid, display_name: game.name,
        app_type: game.isNonSteam ? 1073741824 : 1, rt_last_time_played: game.lastPlayed,
        local_per_client_data: { installed: game.installed } }));
    },
  } });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("gives each requested game a fresh page instead of the previous game's state", async () => {
  await act(async () => { render(<EscaladoresSection />); });
  await act(async () => { openUpscalersFor(1); });
  expect(screen.getByTestId("page").textContent).toBe("1:1");
  await act(async () => { openUpscalersFor(2); });
  expect(screen.getByTestId("page").textContent).toBe("2:2");
});

it("names Mako and Lossless in the list instead of the game's own techniques", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersOverview).mockResolvedValueOnce({ builds: [], installs: {}, job: null, preferred: "fsr",
    engines: { "1": { mako: { spatial: true, fg: true, multiplier: 2 } }, "2": { lossless: { multiplier: 4 } } } } as never);
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({ "1": { inputs: ["DLSS", "XeSS"], native: false } } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("Mako 4 ×2")).toBeTruthy();
  expect(screen.getByText("Lossless ×4")).toBeTruthy();
  expect(screen.queryByText("DLSS, XeSS")).toBeNull();
});

it("leaves out store shortcuts with no installed game behind them", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "1": { inputs: [], native: false, unavailable: "unifideck_not_installed" }, "2": { inputs: [], native: true },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("A")).toBeNull();
  expect(screen.getByText("B")).toBeTruthy();
  expect(screen.getByText("up.list.linux")).toBeTruthy();
});

it("holds shortcuts back until it knows whether a game is behind them", async () => {
  const api = await import("../api");
  games.push({ installed: false, liveAppid: 3, instanceKey: "3", name: "Shortcut", coverUrls: [], lastPlayed: 0, isNonSteam: true });
  let answer: (value: unknown) => void = () => undefined;
  vi.mocked(api.getUpscalersCompat).mockReturnValueOnce(new Promise((resolve) => { answer = resolve; }) as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("Shortcut")).toBeNull();
  expect(screen.getByText("A")).toBeTruthy();
  await act(async () => { answer({ "3": { inputs: ["DLSS"], native: false } }); });
  expect(screen.getByText("Shortcut")).toBeTruthy();
  games.pop();
});

it("asks for compatibility in batches the backend accepts", async () => {
  const api = await import("../api");
  const extra = Array.from({ length: 399 }, (_, i) => ({ installed: true, liveAppid: 1000 + i, instanceKey: `x${i}`, name: `G${i}`, coverUrls: [], lastPlayed: 0, isNonSteam: false }));
  games.push(...extra);
  vi.mocked(api.getUpscalersCompat).mockClear();
  await act(async () => { render(<EscaladoresSection />); });
  const sizes = vi.mocked(api.getUpscalersCompat).mock.calls.map(([ids]) => ids.length);
  expect(sizes).toEqual([400, 1]);
  games.splice(2, extra.length);
});

const requiemManifest = { appid: 3764200, state_flags: 4, name: "Resident Evil Requiem", source: "steam_manifest" };

it.each(["absent", "false", "missing"] as const)("lists a confirmed Steam install with collection state %s", async (collection) => {
  const api = await import("../api");
  const steamOverview = { appid: requiemManifest.appid, display_name: requiemManifest.name, app_type: 1 };
  if (collection !== "absent") {
    vi.stubGlobal("collectionStore", { allAppsCollection: { allApps: [
      { ...steamOverview, local_per_client_data: collection === "false" ? { installed: false } : {} },
    ] } });
  }
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => steamOverview });
  vi.mocked(api.getUpscalersOverview).mockResolvedValueOnce({
    builds: [], installs: {}, job: null, preferred: "fsr",
    installed_steam: { complete: true, appids: [requiemManifest.appid] },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText(requiemManifest.name)).toBeTruthy();
  expect(readSelectorContext().selector?.samples[0]).toEqual({
    appid: requiemManifest.appid, collection: collection !== "absent",
    local: collection === "false" ? "false" : "missing", row: "visible",
  });
  await act(async () => { openUpscalersFor(requiemManifest.appid); });
  expect(screen.getByTestId("page").textContent).toBe("3764200:3764200");
});

it("keeps an installed native shortcut alongside a confirmed Steam install", async () => {
  const api = await import("../api");
  vi.stubGlobal("collectionStore", { allAppsCollection: { allApps: [
    { appid: 3000000123, display_name: "External shortcut", app_type: 1073741824 },
  ] } });
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => ({
    appid: requiemManifest.appid, display_name: requiemManifest.name, app_type: 8,
  }) });
  vi.mocked(api.getUpscalersOverview).mockResolvedValueOnce({
    builds: [], installs: {}, job: null, preferred: "fsr",
    installed_steam: { complete: true, appids: [requiemManifest.appid] },
  } as never);
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "3000000123": { inputs: [], native: true, unavailable: null },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText(requiemManifest.name)).toBeTruthy();
  expect(screen.getByText("External shortcut")).toBeTruthy();
  expect(screen.getByText("up.list.linux")).toBeTruthy();
  expect(readSelectorContext().selector).toMatchObject({ steam_rows: 1, shortcut_rows: 1,
    samples: [{ appid: requiemManifest.appid }] });
});

it("counts rejected manifest candidates without sampling tools or mismatched Steam entries", async () => {
  const api = await import("../api");
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: (appid: number) =>
    appid === 50 ? { appid, app_type: 4, display_name: "Tool" }
      : { appid: 99, app_type: 1, display_name: "Other game" } });
  vi.mocked(api.getUpscalersOverview).mockResolvedValueOnce({
    builds: [], installs: {}, job: null, preferred: "fsr",
    installed_steam: { complete: false, appids: [50, 51] },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("Tool")).toBeNull();
  expect(screen.queryByText("Other game")).toBeNull();
  expect(readSelectorContext().selector).toMatchObject({
    complete: false, filtered: 2, no_metadata: 1, not_game: 1, samples: [{ appid: 1 }, { appid: 2 }],
  });
});

it("keeps an overview failure distinct from an observed empty selector", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersOverview).mockRejectedValueOnce(new Error("RPC unavailable"));
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("load.error")).toBeTruthy();
  expect(readSelectorContext()).toEqual({ selector: null, selector_status: "failed" });
});
