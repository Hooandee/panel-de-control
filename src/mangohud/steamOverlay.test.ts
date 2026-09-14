// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { findModuleExport } from "@decky/ui";

vi.mock("@decky/ui", () => ({ findModuleExport: vi.fn() }));

import { SteamOverlayController } from "./steamOverlay";

afterEach(() => {
  vi.mocked(findModuleExport).mockReset();
  delete (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore;
  delete (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui;
});

function store(level: number | undefined) {
  return {
    msgSettingsGlobal: level === undefined ? undefined : {
      perf_overlay_level: level,
      perf_overlay_service_state: 2,
      is_show_perf_overlay_over_steam_enabled: false,
    },
    SetPerfOverlayLevel: vi.fn(),
  };
}

function installRuntimeStore(perf: ReturnType<typeof store>) {
  class SteamPerfStore {
    static Get() {
      return perf;
    }

    SetPerfOverlayLevel() {}
  }
  const factory = function steamSettingsFactory() {
    return "SetShowPerfOverlayOverSteamEnabled CreateSettingsUpdateRequest";
  };
  const runtime = Object.assign(
    vi.fn(() => ({ SteamPerfStore })),
    { m: { steam: factory } },
  );
  (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
    push: vi.fn(([, , register]) => register(runtime)),
  };
}

describe("SteamOverlayController", () => {
  it("activates Steam's first full HUD preset and confirms its readback", async () => {
    const perf = store(0);
    perf.SetPerfOverlayLevel.mockImplementation((level: number) => {
      perf.msgSettingsGlobal!.perf_overlay_level = level;
    });
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      async () => {},
    );

    const result = await controller.ensureFullHudVisible();

    expect(result.last_activation).toEqual({
      outcome: "confirmed",
      before_level: 0,
      requested_level: 1,
      observed_level: 1,
    });
    expect(result.master_enabled).toBe(true);
    expect(result.ui_level).toBe(2);
  });

  it.each([1, 2, 3, 4])("preserves an active raw level %s", async (level) => {
    const perf = store(level);
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "module" }),
      async () => {},
    );

    const result = await controller.ensureFullHudVisible();

    expect(perf.SetPerfOverlayLevel).not.toHaveBeenCalled();
    expect(result.last_activation).toEqual({
      outcome: "already_visible",
      before_level: level,
      requested_level: null,
      observed_level: level,
    });
  });

  it("keeps an unhydrated store distinct from Steam being hidden", async () => {
    const perf = store(undefined);
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      async () => {},
    );

    const result = await controller.ensureFullHudVisible();

    expect(perf.SetPerfOverlayLevel).not.toHaveBeenCalled();
    expect(result).toMatchObject({
      snapshot_status: "unavailable",
      raw_level: null,
      master_enabled: null,
      last_activation: { outcome: "unavailable" },
    });
  });

  it("waits for Steam settings to hydrate before deciding whether to activate", async () => {
    const perf = store(undefined);
    const waitForHydration = vi.fn(async () => {
      perf.msgSettingsGlobal = {
        perf_overlay_level: 0,
        perf_overlay_service_state: 2,
        is_show_perf_overlay_over_steam_enabled: false,
      };
    });
    perf.SetPerfOverlayLevel.mockImplementation((level: number) => {
      perf.msgSettingsGlobal!.perf_overlay_level = level;
    });
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      waitForHydration,
    );

    const result = await controller.ensureFullHudVisible();

    expect(waitForHydration).toHaveBeenCalled();
    expect(perf.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result.last_activation.outcome).toBe("confirmed");
  });

  it("retries when Steam's store appears after the first lookup", async () => {
    const perf = store(0);
    perf.SetPerfOverlayLevel.mockImplementation((level: number) => {
      perf.msgSettingsGlobal!.perf_overlay_level = level;
    });
    const resolveStore = vi.fn()
      .mockReturnValueOnce(null)
      .mockReturnValue({ store: perf, resolver: "global" });
    const controller = new SteamOverlayController(resolveStore, async () => {}, 2);

    const result = await controller.ensureFullHudVisible();

    expect(resolveStore).toHaveBeenCalled();
    expect(perf.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result.last_activation.outcome).toBe("confirmed");
  });

  it("refreshes Steam's runtime when Decky's module snapshot predates the perf store", async () => {
    const perf = store(0);
    perf.SetPerfOverlayLevel.mockImplementation((level: number) => {
      perf.msgSettingsGlobal!.perf_overlay_level = level;
    });
    installRuntimeStore(perf);
    const controller = new SteamOverlayController(undefined, async () => {});

    const result = await controller.ensureFullHudVisible();

    expect(perf.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({
      resolver: "module",
      raw_level: 1,
      last_activation: { outcome: "confirmed" },
    });
  });

  it("prefers Steam's live runtime store over Decky's stale module snapshot", async () => {
    const stale = store(0);
    class StaleSteamPerfStore {
      static Get() {
        return stale;
      }

      SetPerfOverlayLevel() {}
    }
    vi.mocked(findModuleExport).mockReturnValue(StaleSteamPerfStore);

    const live = store(0);
    live.SetPerfOverlayLevel.mockImplementation((level: number) => {
      live.msgSettingsGlobal!.perf_overlay_level = level;
    });
    installRuntimeStore(live);

    const controller = new SteamOverlayController(undefined, async () => {}, 1);
    const result = await controller.ensureFullHudVisible();

    expect(stale.SetPerfOverlayLevel).not.toHaveBeenCalled();
    expect(live.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result.last_activation.outcome).toBe("confirmed");
  });

  it("skips a partial global store when the live runtime can activate the HUD", async () => {
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgSettingsGlobal: { perf_overlay_level: 0 },
    };
    const live = store(0);
    live.SetPerfOverlayLevel.mockImplementation((level: number) => {
      live.msgSettingsGlobal!.perf_overlay_level = level;
    });
    installRuntimeStore(live);

    const result = await new SteamOverlayController().ensureFullHudVisible();

    expect(live.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result.last_activation.outcome).toBe("confirmed");
  });

  it("uses a hydrated runtime while the global store is still loading", async () => {
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = store(undefined);
    const live = store(0);
    live.SetPerfOverlayLevel.mockImplementation((level: number) => {
      live.msgSettingsGlobal!.perf_overlay_level = level;
    });
    installRuntimeStore(live);

    const result = await new SteamOverlayController().ensureFullHudVisible();

    expect(live.SetPerfOverlayLevel).toHaveBeenCalledWith(1);
    expect(result.last_activation.outcome).toBe("confirmed");
  });

  it("reuses a resolved live runtime store", () => {
    const live = store(1);
    installRuntimeStore(live);
    const chunks = (window as Window & {
      webpackChunksteamui?: { push: ReturnType<typeof vi.fn> };
    }).webpackChunksteamui!;
    const controller = new SteamOverlayController();

    controller.diagnostics();
    controller.diagnostics();

    expect(chunks.push).toHaveBeenCalledOnce();
  });

  it("coalesces concurrent activation attempts", async () => {
    const perf = store(0);
    let finishReadback: (() => void) | undefined;
    const readback = new Promise<void>((resolve) => { finishReadback = resolve; });
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      () => readback,
      1,
    );

    const first = controller.ensureFullHudVisible();
    const second = controller.ensureFullHudVisible();

    expect(perf.SetPerfOverlayLevel).toHaveBeenCalledOnce();
    perf.msgSettingsGlobal!.perf_overlay_level = 1;
    finishReadback?.();
    await expect(Promise.all([first, second])).resolves.toEqual([
      expect.objectContaining({ raw_level: 1 }),
      expect.objectContaining({ raw_level: 1 }),
    ]);
  });

  it("cancels a pending activation before it can write", async () => {
    const perf = store(0);
    let resolved: { store: typeof perf; resolver: "global" } | null = null;
    let finishWait: (() => void) | undefined;
    const waiting = new Promise<void>((resolve) => { finishWait = resolve; });
    const controller = new SteamOverlayController(() => resolved, () => waiting, 1);

    const activation = controller.ensureFullHudVisible();
    controller.cancelActivation();
    resolved = { store: perf, resolver: "global" };
    finishWait?.();
    await activation;

    expect(perf.SetPerfOverlayLevel).not.toHaveBeenCalled();
  });

  it("does not claim success when Steam never confirms the requested level", async () => {
    const perf = store(0);
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      async () => {},
      2,
    );

    const result = await controller.ensureFullHudVisible();

    expect(perf.SetPerfOverlayLevel).toHaveBeenCalledOnce();
    expect(result.last_activation).toEqual({
      outcome: "readback_timeout",
      before_level: 0,
      requested_level: 1,
      observed_level: 0,
    });
    expect(result.master_enabled).toBe(false);
  });

  it("reports a setter exception without exposing its text", async () => {
    const perf = store(0);
    perf.SetPerfOverlayLevel.mockImplementation(() => {
      throw new Error("PRIVATE INTERNAL ERROR");
    });
    const controller = new SteamOverlayController(
      () => ({ store: perf, resolver: "global" }),
      async () => {},
    );

    const result = await controller.ensureFullHudVisible();

    expect(result.last_activation).toEqual({
      outcome: "exception",
      before_level: 0,
      requested_level: 1,
      observed_level: 0,
    });
    expect(JSON.stringify(result)).not.toContain("PRIVATE");
  });
});
