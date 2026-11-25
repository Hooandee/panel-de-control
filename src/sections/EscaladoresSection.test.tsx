// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const games = vi.hoisted(() => [
  { installed: true, liveAppid: 1, instanceKey: "1", name: "A", coverUrls: [], lastPlayed: 2, isNonSteam: false },
  { installed: true, liveAppid: 2, instanceKey: "2", name: "B", coverUrls: [], lastPlayed: 1, isNonSteam: false },
]);
vi.mock("@decky/ui", () => ({ Focusable: ({ children }: any) => <div>{children}</div> }));
vi.mock("../api", () => ({
  getUpscalersOverview: vi.fn(async () => ({ builds: [], installs: {}, job: null, preferred: "fsr" })),
  getUpscalersSelectorInstalls: vi.fn(async () => ({ complete: true, appids: [] as number[] })),
  getUpscalersCompat: vi.fn(async () => ({})),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/FocusableCard", () => ({ FocusableCard: ({ children }: any) => <div>{children}</div> }));
vi.mock("../components/GameCover", () => ({ GameCover: () => null }));
vi.mock("../upscalers/BulkPanel", () => ({ BulkPanel: ({ onChanged }: { onChanged: () => void }) => <button onClick={onChanged}>Refresh</button> }));
vi.mock("../upscalers/overlays", () => ({
  IN_GAME_MODES: [], reportedAppids: vi.fn(() => []), publishOverview: vi.fn(), readInGameMode: () => "start", setUpscalersSectionOpen: vi.fn(), writeInGameMode: vi.fn(), readCoverBadges: () => true, writeCoverBadges: vi.fn(),
}));
vi.mock("../upscalers/pageMemory", () => ({ showGame: vi.fn(), takeHeldPage: () => null }));
vi.mock("../upscalers/GameView", () => ({
  GameView: ({ game }: { game: { liveAppid: number } }) => {
    const [firstAppid] = useState(game.liveAppid);
    return <output data-testid="page">{`${firstAppid}:${game.liveAppid}`}</output>;
  },
}));

import { openUpscalersFor } from "../upscalers/deepLink";
import { upscalersReportContext } from "../report/upscalersContext";
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

it("lists an installed store game Panel cannot act on with its reason, without opening it", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "1": { inputs: [], native: false, unavailable: "unifideck_no_exe" }, "2": { inputs: [], native: true },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("A")).toBeTruthy();
  expect(screen.getByText("up.list.unavailable.unifideck_no_exe")).toBeTruthy();
  expect(readSelectorContext().selector).toMatchObject({ filtered: 0, unavailable: { unifideck_no_exe: 1 } });
});

it("holds shortcuts back until it knows whether a game is behind them", async () => {
  const api = await import("../api");
  games.push({ installed: false, liveAppid: 3, instanceKey: "3", name: "Shortcut", coverUrls: [], lastPlayed: 0, isNonSteam: true });
  let answer: (value: unknown) => void = () => undefined;
  vi.mocked(api.getUpscalersCompat).mockImplementation((ids) => ids.includes("3")
    ? new Promise((resolve) => { answer = resolve; }) as never : Promise.resolve({}));
  try {
    await act(async () => { render(<EscaladoresSection />); });
    expect(screen.queryByText("Shortcut")).toBeNull();
    expect(screen.getByText("A")).toBeTruthy();
    await act(async () => { answer({ "3": { inputs: ["DLSS"], native: false } }); });
    expect(screen.getByText("Shortcut")).toBeTruthy();
  } finally {
    games.pop();
    vi.mocked(api.getUpscalersCompat).mockImplementation(async () => ({}));
  }
});

it("lists shortcuts as soon as their own check answers, however slow the Steam games are", async () => {
  const api = await import("../api");
  games.push(
    { installed: false, liveAppid: 3, instanceKey: "3", name: "Shortcut", coverUrls: [], lastPlayed: 0, isNonSteam: true },
    { installed: false, liveAppid: 4, instanceKey: "4", name: "Store shortcut", coverUrls: [], lastPlayed: 0, isNonSteam: true },
  );
  vi.mocked(api.getUpscalersCompat).mockImplementation((ids) => ids.includes("1")
    ? new Promise(() => undefined) as never
    : Promise.resolve({ "3": { inputs: [], native: true }, "4": { inputs: [], native: false, unavailable: "unifideck_not_installed" } }) as never);
  try {
    await act(async () => { render(<EscaladoresSection />); });
    expect(screen.getByText("Shortcut")).toBeTruthy();
    expect(screen.queryByText("Store shortcut")).toBeNull();
    expect(screen.getByText("A")).toBeTruthy();
  } finally {
    games.splice(2, 2);
    vi.mocked(api.getUpscalersCompat).mockImplementation(async () => ({}));
  }
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

const requiem = { appid: 3764200, name: "Resident Evil Requiem" };

it.each(["absent", "false", "missing"] as const)("lists a confirmed Steam install with collection state %s", async (collection) => {
  const api = await import("../api");
  const steamOverview = { appid: requiem.appid, display_name: requiem.name, app_type: 1 };
  if (collection !== "absent") {
    vi.stubGlobal("collectionStore", { allAppsCollection: { allApps: [
      { ...steamOverview, local_per_client_data: collection === "false" ? { installed: false } : {} },
    ] } });
  }
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => steamOverview });
  vi.mocked(api.getUpscalersSelectorInstalls).mockResolvedValueOnce({ complete: true, appids: [requiem.appid] });
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText(requiem.name)).toBeTruthy();
  const report = await upscalersReportContext();
  expect(report.selector?.samples[0]).toEqual({
    appid: requiem.appid, collection: collection !== "absent", manifest: true,
    local: collection === "false" ? "false" : "missing", row: "visible",
  });
  await act(async () => { openUpscalersFor(requiem.appid); });
  expect(screen.getByTestId("page").textContent).toBe("3764200:3764200");
});

it("keeps an installed native shortcut alongside a confirmed Steam install", async () => {
  const api = await import("../api");
  vi.stubGlobal("collectionStore", { allAppsCollection: { allApps: [
    { appid: 3000000123, display_name: "External shortcut", app_type: 1073741824 },
  ] } });
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => ({
    appid: requiem.appid, display_name: requiem.name, app_type: 8,
  }) });
  vi.mocked(api.getUpscalersSelectorInstalls).mockResolvedValueOnce({ complete: true, appids: [requiem.appid] });
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "3000000123": { inputs: [], native: true, unavailable: null },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText(requiem.name)).toBeTruthy();
  expect(screen.getByText("External shortcut")).toBeTruthy();
  expect(screen.getByText("up.list.linux")).toBeTruthy();
  expect(readSelectorContext().selector).toMatchObject({ steam_rows: 1, shortcut_rows: 1,
    samples: [{ appid: requiem.appid }] });
});

it("counts rejected manifest candidates without sampling tools or mismatched Steam entries", async () => {
  const api = await import("../api");
  const { reportedAppids } = await import("../upscalers/overlays");
  vi.mocked(reportedAppids).mockReturnValueOnce(["50", "51"]);
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: (appid: number) =>
    appid === 50 ? { appid, app_type: 4, display_name: "Tool" }
      : { appid: 99, app_type: 1, display_name: "Other game" } });
  vi.mocked(api.getUpscalersSelectorInstalls).mockResolvedValueOnce({ complete: false, appids: [50, 51, 52] });
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("Tool")).toBeNull();
  expect(screen.queryByText("Other game")).toBeNull();
  expect(readSelectorContext().selector).toMatchObject({
    complete: false, filtered: 0, no_metadata: 2, not_game: 1, samples: [{ appid: 1 }, { appid: 2 }],
  });
  expect((await upscalersReportContext()).selector).toHaveProperty("omissions", [{ appid: 51, reason: "no_metadata" }]);
});

it("drops the old compatibility of an entry removed and added back to the collection", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "1": { native: false, inputs: [], unavailable: "unifideck_not_installed" }, "2": { native: true, inputs: [] },
  });
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("A")).toBeNull();
  games[0].installed = false;
  try {
    await act(async () => { fireEvent.click(screen.getByText("Refresh")); });
  } finally {
    games[0].installed = true;
  }
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({});
  await act(async () => { fireEvent.click(screen.getByText("Refresh")); });
  expect(screen.getByText("A")).toBeTruthy();
  expect(readSelectorContext().selector).toMatchObject({ compatibility: "partial", filtered: 0 });
});

it("keeps an overview failure distinct from an observed empty selector", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersOverview).mockRejectedValueOnce(new Error("RPC unavailable"));
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("load.error")).toBeTruthy();
  expect(readSelectorContext()).toEqual({ selector: null, selector_status: "failed" });
});

it("keeps reporting visible rows when a refresh fails and ignores older replies", async () => {
  const api = await import("../api");
  await act(async () => { render(<EscaladoresSection />); });
  let rejectOlder!: (error: Error) => void;
  vi.mocked(api.getUpscalersOverview).mockReturnValueOnce(new Promise((_, reject) => { rejectOlder = reject; }));
  await act(async () => { fireEvent.click(screen.getByText("Refresh")); });
  await act(async () => { fireEvent.click(screen.getByText("Refresh")); });
  await act(async () => { rejectOlder(Error("stale")); });
  expect(screen.queryByText("load.error")).toBeNull();

  vi.mocked(api.getUpscalersOverview).mockRejectedValueOnce(Error("unavailable"));
  await act(async () => { fireEvent.click(screen.getByText("Refresh")); });
  expect(screen.getByText("load.error")).toBeTruthy();
  expect(screen.getByText("A")).toBeTruthy();
  expect(readSelectorContext()).toMatchObject({ selector_status: "observed", selector: { steam_rows: 2 } });
});

it("shows the normal list while the manifest RPC waits and opens its pending game on arrival", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersCompat).mockClear();
  let finishCompat!: (result: {}) => void;
  vi.mocked(api.getUpscalersCompat).mockReturnValueOnce(new Promise((resolve) => { finishCompat = resolve; }));
  let finish!: (result: { complete: boolean; appids: number[] }) => void;
  vi.mocked(api.getUpscalersSelectorInstalls).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => ({
    appid: requiem.appid, display_name: requiem.name, app_type: 1,
  }) });
  await act(async () => { openUpscalersFor(requiem.appid); render(<EscaladoresSection />); });
  expect(screen.getByText("A")).toBeTruthy();
  expect(screen.queryByTestId("page")).toBeNull();
  await act(async () => { finish({ complete: true, appids: [requiem.appid] }); });
  expect(screen.getByTestId("page").textContent).toBe("3764200:3764200");
  expect(vi.mocked(api.getUpscalersCompat).mock.calls.map(([ids]) => ids)).toEqual([["1", "2"], ["3764200"]]);
  await act(async () => { finishCompat({}); });
});

it("skips unreadable Steam entries without hiding healthy rows", async () => {
  vi.stubGlobal("collectionStore", { allAppsCollection: { allApps: [
    { get appid() { throw Error("unreadable id"); } },
    { appid: 10, app_type: 1, get local_per_client_data() { throw Error("unreadable flag"); } },
    { appid: 11, app_type: 1, local_per_client_data: { installed: true }, get display_name() { throw Error("unreadable name"); } },
    { appid: 12, app_type: 1, local_per_client_data: { installed: true }, display_name: "Healthy game" },
  ] } });
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("Healthy game")).toBeTruthy();
  expect(readSelectorContext().selector).toMatchObject({ unreadable: 3, steam_rows: 1 });
});

it("asks a slow inventory once more and lists the game it confirms later", async () => {
  vi.useFakeTimers();
  try {
    const api = await import("../api");
    vi.stubGlobal("appStore", { GetAppOverviewByAppID: () => ({ appid: requiem.appid, display_name: requiem.name, app_type: 1 }) });
    vi.mocked(api.getUpscalersSelectorInstalls).mockClear()
      .mockResolvedValueOnce({ complete: false, appids: [] })
      .mockResolvedValueOnce({ complete: false, appids: [requiem.appid], rejected: { not_installed: 1 } });
    await act(async () => { render(<EscaladoresSection />); });
    expect(screen.queryByText(requiem.name)).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(screen.getByText(requiem.name)).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(api.getUpscalersSelectorInstalls).toHaveBeenCalledTimes(2);
    expect(readSelectorContext().selector).toMatchObject({ manifest_rejected: { not_installed: 1 } });
  } finally {
    vi.useRealTimers();
  }
});
