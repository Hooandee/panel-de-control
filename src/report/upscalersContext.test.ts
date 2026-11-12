import { afterEach, expect, it, vi } from "vitest";

vi.mock("../launch/steamApi", () => ({ listInstalledGames: vi.fn(() => []) }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: vi.fn(() => null) }));
vi.mock("../upscalers/overlays", () => ({ reportedAppids: vi.fn(() => []), readCoverBadges: () => true, readInGameMode: () => "off" }));
import { listInstalledGames } from "../launch/steamApi";
import { readRunningGame } from "../tdp/runningGame";
import { reportedAppids } from "../upscalers/overlays";
import { steamFacts, upscalersReportContext } from "./upscalersContext";

afterEach(() => { vi.resetAllMocks(); delete (globalThis as any).SteamClient; delete (globalThis as any).App; });

it("records no observed game without RPC dependencies", async () => {
  expect(await upscalersReportContext()).toEqual({ collected_at: expect.any(String), status: "available", badges: { covers: true, in_game: "off" }, running: null, games: {} });
  expect(listInstalledGames).not.toHaveBeenCalled();
});

it.each([
  ["123", 123, false],
  ["ns:my-game", 3456789, true],
] as const)("keeps stable and live identities separate for %s", async (appid, liveAppid, isNonSteam) => {
  vi.mocked(readRunningGame).mockReturnValue({ appid, liveAppid, name: "Game" });
  vi.mocked(listInstalledGames).mockReturnValue([{ liveAppid, isNonSteam, launchOptions: "SECRET=token" } as any]);
  const result = await upscalersReportContext();
  expect(result.running).toEqual({ stable_appid: appid, live_appid: String(liveAppid), name: "Game", is_non_steam: isNonSteam });
});

it("does not use another shortcut's identity and bounds text", async () => {
  vi.mocked(readRunningGame).mockReturnValue({ appid: "ns:" + "x".repeat(500), liveAppid: 99, name: "n".repeat(500) });
  vi.mocked(listInstalledGames).mockReturnValue([{ liveAppid: 98, isNonSteam: true } as any]);
  const result = await upscalersReportContext();
  expect(result.running?.is_non_steam).toBeNull();
  expect(result.running?.name).toHaveLength(256);
  expect(result.running?.stable_appid).toHaveLength(256);
});

it("degrades to partial context without preventing a report", async () => {
  vi.mocked(readRunningGame).mockImplementation(() => { throw new Error("unavailable"); });
  expect(await upscalersReportContext()).toEqual({ collected_at: expect.any(String), status: "unavailable", badges: { covers: true, in_game: "off" }, running: null, games: {} });
});

it("adds Steam's live facts for every game Panel set up, without the owner's id", async () => {
  vi.mocked(reportedAppids).mockReturnValue(["3764200"]);
  (globalThis as any).App = { m_CurrentUser: { strSteamID: "76561198000000001" } };
  (globalThis as any).SteamClient = { Apps: { RegisterForAppDetails: (_appid: number, callback: (d: unknown) => void) => {
    callback({ eAppOwnershipFlags: 2049, strOwnerSteamID: "76561198000000001", bIsFreeApp: false, strSelectedBeta: "public",
      nBuildID: 23634047, strCompatToolName: "proton_experimental", strLaunchOptions: 'WINEDLLOVERRIDES="dxgi=n,b" %command%' });
    return { unregister: () => undefined };
  } } };
  const result = await upscalersReportContext();
  expect(result.games["3764200"]).toEqual({ ownership_flags: 2049, owned_by_user: true, free: false, beta: "public",
    build_id: 23634047, compat_tool: "proton_experimental", launch_options: 'WINEDLLOVERRIDES="dxgi=n,b" %command%' });
  expect(JSON.stringify(result)).not.toContain("76561198000000001");
});

it("says a borrowed licence is not the user's", () => {
  expect(steamFacts({ strOwnerSteamID: "111" }, "222").owned_by_user).toBe(false);
  expect(steamFacts({}, "222").owned_by_user).toBeNull();
});
