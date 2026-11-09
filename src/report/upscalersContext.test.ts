import { afterEach, expect, it, vi } from "vitest";

vi.mock("../launch/steamApi", () => ({ listInstalledGames: vi.fn(() => []) }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: vi.fn(() => null) }));
import { listInstalledGames } from "../launch/steamApi";
import { readRunningGame } from "../tdp/runningGame";
import { upscalersReportContext } from "./upscalersContext";

afterEach(() => { vi.resetAllMocks(); });

it("records no observed game without adding launch options or RPC dependencies", () => {
  expect(upscalersReportContext()).toEqual({ collected_at: expect.any(String), status: "available", running: null });
  expect(listInstalledGames).not.toHaveBeenCalled();
});

it.each([
  ["123", 123, false],
  ["ns:my-game", 3456789, true],
] as const)("keeps stable and live identities separate for %s", (appid, liveAppid, isNonSteam) => {
  vi.mocked(readRunningGame).mockReturnValue({ appid, liveAppid, name: "Game" });
  vi.mocked(listInstalledGames).mockReturnValue([{ liveAppid, isNonSteam, launchOptions: "SECRET=token" } as any]);
  expect(upscalersReportContext()).toEqual({ collected_at: expect.any(String), status: "available",
    running: { stable_appid: appid, live_appid: String(liveAppid), name: "Game", is_non_steam: isNonSteam } });
});

it("does not use another shortcut's identity and bounds text", () => {
  vi.mocked(readRunningGame).mockReturnValue({ appid: "ns:" + "x".repeat(500), liveAppid: 99, name: "n".repeat(500) });
  vi.mocked(listInstalledGames).mockReturnValue([{ liveAppid: 98, isNonSteam: true } as any]);
  const result = upscalersReportContext();
  expect(result.running?.is_non_steam).toBeNull();
  expect(result.running?.name).toHaveLength(256);
  expect(result.running?.stable_appid).toHaveLength(256);
});

it("degrades to partial context without preventing a report", () => {
  vi.mocked(readRunningGame).mockImplementation(() => { throw new Error("unavailable"); });
  expect(upscalersReportContext()).toEqual({ collected_at: expect.any(String), status: "unavailable", running: null });
});
