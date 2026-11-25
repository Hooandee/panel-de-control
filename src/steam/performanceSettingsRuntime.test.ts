// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ runtime: vi.fn() }));
vi.mock("./performanceRuntime", () => ({ currentSteamRuntime: mocks.runtime, resolveSteamPerformanceStore: () => null }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: () => null }));
import { createPerformanceSettingsDeps } from "./performanceSettingsRuntime";

function source<T extends Function>(fn: T, text: string): T {
  Object.defineProperty(fn, "toString", { value: () => text });
  return fn;
}
function fixture() {
  const cache = new Map<string, unknown>();
  const client = { getQueryData: (key: string[]) => cache.get(key.join("/")),
    fetchQuery: vi.fn(async ({ queryKey, queryFn }: { queryKey: string[]; queryFn: () => Promise<unknown> }) => {
      const result = await queryFn(); cache.set(queryKey.join("/"), result); return result;
    }) };
  const gamescopeRead = vi.fn(async () => ({ BSuccess: (): boolean => true,
    Body: () => ({ toObject: () => ({ state: { is_app_refresh_rate_supported: true } }) }) }));
  const managerRead = vi.fn(async () => ({ BSuccess: (): boolean => true,
    Body: () => ({ toObject: () => ({ state: { is_vrs_available: true } }) }) }));
  source(gamescopeRead, 'SendMsg("Gamescope.GetState#1")');
  source(managerRead, 'SendMsg("SteamOSManager.GetState#1")');
  const displayRead = vi.fn(async () => ({ displays: [{ is_primary: true, is_internal: true, is_vrr_capable: false }] }));
  class DisplayStore { static Get() { return new DisplayStore(); } GetState() { return displayRead(); } }
  const modules: Record<string, Record<string, unknown>> = {
    query: { client }, game: { service: { GetState: gamescopeRead } },
    os: { service: { GetState: managerRead } }, display: { DisplayStore },
  };
  const factories = {
    query: source(() => {}, "ReactQueryDevtools offlineFirst"),
    game: source(() => {}, "Gamescope.GetState#1"),
    os: source(() => {}, "SteamOSManager.GetState#1"),
    display: source(() => {}, "CSystemDisplayManagerStore Failed to fetch display manager state"),
  };
  const runtime = Object.assign((id: string) => modules[id], { m: factories });
  mocks.runtime.mockReturnValue(runtime);
  return { cache, client, modules, runtime, gamescopeRead, managerRead, displayRead, deps: createPerformanceSettingsDeps() };
}
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }
afterEach(() => vi.useRealTimers());

describe("performance settings capability hydration", () => {
  it("hydrates all capability queries without mounting native controls and deduplicates reads", async () => {
    const { deps, client, gamescopeRead, managerRead, displayRead } = fixture();
    expect(deps.gamescope()).toBeNull(); expect(deps.steamOs()).toBeNull(); expect(deps.display()).toBeNull();
    deps.gamescope(); deps.steamOs(); deps.display();
    await flush();
    expect(client.fetchQuery).toHaveBeenCalledTimes(3);
    expect(gamescopeRead).toHaveBeenCalledExactlyOnceWith({});
    expect(managerRead).toHaveBeenCalledExactlyOnceWith({});
    expect(displayRead).toHaveBeenCalledOnce();
    expect(deps.gamescope()).toMatchObject({ is_app_refresh_rate_supported: true });
    expect(deps.steamOs()).toMatchObject({ is_vrs_available: true });
    expect(deps.display()).toMatchObject({ external: false, isVrrCapable: false });
  });
  it("preserves populated queries without requesting a capability again", async () => {
    const { deps, cache, client } = fixture();
    cache.set("GamescopeService/State", { is_app_refresh_rate_supported: false });
    expect(deps.gamescope()).toEqual({ is_app_refresh_rate_supported: false });
    await flush(); expect(client.fetchQuery).not.toHaveBeenCalled();
  });
  it("does not hydrate ambiguous service exports", async () => {
    const { deps, modules, client } = fixture();
    modules.game.other = { GetState: source(vi.fn(), 'SendMsg("Gamescope.GetState#1")') };
    expect(deps.gamescope()).toBeNull(); await flush(); expect(client.fetchQuery).not.toHaveBeenCalled();
  });
  it("does not choose an ambiguous query client", async () => {
    const { deps, modules, client } = fixture();
    modules.query.other = { getQueryData: () => undefined };
    expect(deps.gamescope()).toBeNull(); await flush(); expect(client.fetchQuery).not.toHaveBeenCalled();
  });
  it("does not turn a failed service reply into confirmed capabilities and backs off", async () => {
    vi.useFakeTimers();
    const { deps, gamescopeRead } = fixture();
    gamescopeRead.mockResolvedValue({ BSuccess: () => false,
      Body: () => ({ toObject: () => ({ state: { is_app_refresh_rate_supported: true } }) }) });
    deps.gamescope(); await flush();
    expect(deps.gamescope()).toBeNull(); await flush();
    expect(gamescopeRead).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(5000); deps.gamescope(); await flush();
    expect(gamescopeRead).toHaveBeenCalledTimes(2);
  });
  it("leaves incomplete display capability unknown", async () => {
    const { deps, displayRead } = fixture();
    displayRead.mockResolvedValue({ displays: [] });
    deps.display(); await flush(); expect(deps.display()).toBeNull();
  });
  it("bounds stalled queries and does not accept a late reply as current capability", async () => {
    vi.useFakeTimers();
    const { deps, gamescopeRead } = fixture();
    let finish!: (value: Awaited<ReturnType<typeof gamescopeRead>>) => void;
    gamescopeRead.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    deps.gamescope(); await flush();
    await vi.advanceTimersByTimeAsync(4000);
    finish({ BSuccess: (): boolean => true, Body: () => ({ toObject: () => ({ state: { is_app_refresh_rate_supported: true } }) }) });
    await flush(); expect(deps.gamescope()).toBeNull(); expect(gamescopeRead).toHaveBeenCalledOnce();
  });
});
