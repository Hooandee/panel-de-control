import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LaunchReceipt } from "./launchOwnership";

const state = vi.hoisted(() => ({ launch: "", receipt: null as LaunchReceipt | null, failWrite: false, failSave: false, ignoreWrite: false, keys: [] as string[] }));
vi.mock("../api", () => ({
  getUpscalerLaunchReceipt: vi.fn(async () => state.receipt),
  setUpscalerLaunchReceipt: vi.fn(async (appid: string, owner: string, receipt: LaunchReceipt) => {
    if (state.failSave) return false;
    state.keys.push(`${appid}/${owner}`);
    state.receipt = structuredClone(receipt);
    return true;
  }),
}));
vi.mock("../launch/steamApi", () => ({
  readAppDetails: vi.fn(async () => ({ launch: state.launch })),
  writeLaunchOptions: vi.fn((_id: number, value: string) => {
    if (state.failWrite) return false;
    if (!state.ignoreWrite) state.launch = value;
    return true;
  }),
}));
import { applyManagedLaunch } from "./managedLaunch";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { getUpscalerLaunchReceipt, setUpscalerLaunchReceipt } from "../api";

describe("managed launch receipt", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.launch = "%command% -dx12";
    state.receipt = null;
    state.failWrite = state.failSave = state.ignoreWrite = false;
    state.keys = [];
  });

  it("does not write launch options when ownership preparation fails", async () => {
    const beforeApply = vi.fn(async () => { throw new Error("record_failed"); });
    const result = await applyManagedLaunch("1", 1, "upscaler", { env: { TEST: "1" } }, { beforeApply });
    expect(result.ok).toBe(false);
    expect(beforeApply).toHaveBeenCalledOnce();
    expect(writeLaunchOptions).not.toHaveBeenCalled();
    expect(state.launch).toBe("%command% -dx12");
  });

  it("stores recoverable ownership under stable identity and confirms launch before success", async () => {
    expect((await applyManagedLaunch("ns:Game", 3000000001, "mako", { wrappers: ["~/.local/bin/mako-run"] }, { isNonSteam: true })).ok).toBe(true);
    expect(state.launch).toBe("~/.local/bin/mako-run %command% -dx12");
    expect(state.keys).toEqual(["ns:Game/mako", "ns:Game/mako"]);
    expect(writeLaunchOptions).toHaveBeenCalledWith(3000000001, state.launch, true, true);
    expect((await applyManagedLaunch("ns:Game", 3000000002, "mako", {}, { isNonSteam: true })).ok).toBe(true);
    expect(state.launch).toBe("%command% -dx12");
  });

  it("keeps custom env and returns the preservation warning without claiming ownership", async () => {
    state.launch = 'LSFGVK_PROFILE="custom profile" %command%';
    const result = await applyManagedLaunch("1", 1, "lsfg", { env: { LSFGVK_PROFILE: "pdc-1" } });
    expect(result).toEqual({ ok: true, preserved: { env: ["LSFGVK_PROFILE"], wrappers: [] } });
    expect(state.launch).toBe('LSFGVK_PROFILE="custom profile" %command%');
    expect(state.receipt?.env).toEqual([]);
  });

  it("preserves a user-edited value during uninstall", async () => {
    await applyManagedLaunch("1", 1, "lsfg", { env: { LSFGVK_PROFILE: "pdc-1" } });
    state.launch = 'LSFGVK_PROFILE="new profile" %command% -dx12';
    expect((await applyManagedLaunch("1", 1, "lsfg", {})).preserved.env).toEqual(["LSFGVK_PROFILE"]);
    expect(state.launch).toContain('LSFGVK_PROFILE="new profile"');
  });

  it("retains ownership intent after rejected or unconfirmed writes", async () => {
    state.failWrite = true;
    expect((await applyManagedLaunch("1", 1, "lsfg", { env: { LSFGVK_PROFILE: "pdc-1" } })).ok).toBe(false);
    state.failWrite = false;
    state.ignoreWrite = true;
    expect((await applyManagedLaunch("1", 1, "lsfg", { env: { LSFGVK_PROFILE: "pdc-1" } })).ok).toBe(false);
    expect(setUpscalerLaunchReceipt).toHaveBeenCalled();
    expect(state.receipt?.env[0].name).toBe("LSFGVK_PROFILE");
    expect(state.launch).toBe("%command% -dx12");
  });

  it("does not write when ownership intent cannot be persisted", async () => {
    state.failSave = true;
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-run"] })).ok).toBe(false);
    expect(state.launch).toBe("%command% -dx12");
    expect(state.receipt).toBeNull();
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });

  it("does not roll back over a user edit arriving while receipt persistence fails", async () => {
    vi.mocked(setUpscalerLaunchReceipt).mockImplementationOnce(async () => { state.launch = "%command% --user-edited"; return false; });
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-run"] })).ok).toBe(false);
    expect(state.launch).toBe("%command% --user-edited");
  });

  it("rejects unreadable or ambiguous options and receipt read failures before writing", async () => {
    vi.mocked(readAppDetails).mockResolvedValueOnce(null);
    expect((await applyManagedLaunch("1", 1, "mako", {})).ok).toBe(false);
    state.launch = 'sh -c "%command%"';
    expect((await applyManagedLaunch("1", 1, "mako", {})).ok).toBe(false);
    vi.mocked(getUpscalerLaunchReceipt).mockRejectedValueOnce(new Error("private detail"));
    expect((await applyManagedLaunch("1", 1, "mako", {})).ok).toBe(false);
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });

  it("writes a legacy transformation and managed env atomically", async () => {
    expect((await applyManagedLaunch("1", 1, "upscaler", { env: { FSR4_UPGRADE: "1" } }, { transform: (value) => value.replace("-dx12", "-dx11") })).ok).toBe(true);
    expect(state.launch).toBe("FSR4_UPGRADE=1 %command% -dx11");
    expect(writeLaunchOptions).toHaveBeenCalledTimes(1);
  });

  it("does not overwrite an edit arriving while ownership is being read", async () => {
    vi.mocked(getUpscalerLaunchReceipt).mockImplementationOnce(async () => { state.launch = "%command% --edited-during-read"; return null; });
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-run"] })).ok).toBe(false);
    expect(state.launch).toBe("%command% --edited-during-read");
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });

  it("rejects a partial activation before writing when an external wrapper must be preserved", async () => {
    state.launch = "mako-run --custom %command%";
    const next = await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-launch"], env: { MAKO_CONFIG: '"/tmp/owned"' } }, { requireComplete: true });
    expect(next.ok).toBe(false);
    expect(next.preserved.wrappers).toEqual(["mako-run"]);
    expect(state.launch).toBe("mako-run --custom %command%");
    expect(writeLaunchOptions).not.toHaveBeenCalled();
    expect(setUpscalerLaunchReceipt).not.toHaveBeenCalled();
  });


it("keeps recoverable ownership when Steam writes but every readback is unavailable", async () => {
  vi.mocked(readAppDetails).mockResolvedValueOnce({ launch: state.launch } as never)
    .mockResolvedValueOnce({ launch: state.launch } as never)
    .mockResolvedValueOnce({ launch: state.launch } as never)
    .mockResolvedValueOnce(null).mockResolvedValueOnce(null).mockResolvedValueOnce(null);
  const result = await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-run"] });
  expect(result).toMatchObject({ ok: false, pending: true });
  expect(state.launch).toBe("~/.local/bin/mako-run %command% -dx12");
  expect(state.receipt).not.toBeNull();
  expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["~/.local/bin/mako-run"] }, { requireComplete: true })).ok).toBe(true);
});


  it("accepts a late readback after unavailable and rejected reads", async () => {
    vi.mocked(readAppDetails).mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce(null).mockRejectedValueOnce(new Error("unavailable"));
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] })).ok).toBe(true);
    expect(state.launch).toBe("mako-run %command% -dx12");
  });

  it("does not replace a user edit after an uncertain write", async () => {
    vi.mocked(readAppDetails).mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce({ launch: state.launch } as never)
      .mockResolvedValueOnce(null).mockResolvedValueOnce(null).mockResolvedValueOnce(null);
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"], env: { MAKO_CONFIG: "owned" } })).pending).toBe(true);
    state.launch = "MAKO_CONFIG=custom mako-run --custom %command% -dx12";
    vi.mocked(writeLaunchOptions).mockClear();
    const result = await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"], env: { MAKO_CONFIG: "owned" } }, { requireComplete: true });
    expect(result.ok).toBe(false);
    expect(state.launch).toBe("MAKO_CONFIG=custom mako-run --custom %command% -dx12");
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });

  it("can retry removal when Steam ignored the first write", async () => {
    await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"], env: { MAKO_CONFIG: "owned" } });
    state.ignoreWrite = true;
    expect((await applyManagedLaunch("1", 1, "mako", {})).pending).toBe(true);
    expect(state.receipt?.wrappers.added).toEqual(["mako-run"]);
    state.ignoreWrite = false;
    expect((await applyManagedLaunch("1", 1, "mako", {})).ok).toBe(true);
    expect(state.launch).toBe("%command% -dx12");
  });

  it("keeps recovery intent when final receipt persistence fails", async () => {
    vi.mocked(setUpscalerLaunchReceipt).mockImplementationOnce(async (_appid, _owner, receipt) => {
      state.receipt = structuredClone(receipt);
      state.failSave = true;
      return true;
    });
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] }))).toMatchObject({ ok: false, pending: true });
    expect(state.receipt?.wrappers.added).toEqual(["mako-run"]);
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] }, { requireComplete: true })).pending).toBe(true);
    state.failSave = false;
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] }, { requireComplete: true })).ok).toBe(true);
  });

  it("preserves user edits arriving while the intent is persisted", async () => {
    vi.mocked(setUpscalerLaunchReceipt).mockImplementationOnce(async (_appid, _owner, receipt) => {
      state.receipt = structuredClone(receipt);
      state.launch = "%command% --user-edited";
      return true;
    });
    expect((await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] })).ok).toBe(false);
    expect(state.launch).toBe("%command% --user-edited");
    expect(writeLaunchOptions).not.toHaveBeenCalled();
    expect(state.receipt?.pending).not.toBe(true);
  });

  it("reports pending ownership even when launch options cannot be read on retry", async () => {
    state.receipt = { version: 1, pending: true, env: [], wrappers: { before: [], applied: ["mako-run"], added: ["mako-run"] } };
    vi.mocked(readAppDetails).mockResolvedValueOnce(null);
    expect(await applyManagedLaunch("1", 1, "mako", { wrappers: ["mako-run"] })).toMatchObject({ ok: false, pending: true });
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });
});

describe("Lossless explicit configuration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.launch = 'CUSTOM=1 gamemoderun %command% -dx12 --user-option';
    state.receipt = null;
    state.failWrite = state.failSave = state.ignoreWrite = false;
    state.keys = [];
  });
  const env = { LSFGVK_PROFILE: "pdc-1", LSFGVK_CONFIG: "'/home/game user/.config/lsfg-vk/conf.toml'" };
  it("adds the file to an older receipt and restores wrappers and user arguments on disable", async () => {
    const original = state.launch;
    await applyManagedLaunch("1", 1, "lsfg", { env: { LSFGVK_PROFILE: "pdc-1" } }, { requireComplete: true });
    expect((await applyManagedLaunch("1", 1, "lsfg", { env }, { requireComplete: true })).ok).toBe(true);
    expect(state.launch).toContain("LSFGVK_CONFIG=" + env.LSFGVK_CONFIG);
    expect(state.launch).toContain("gamemoderun %command% -dx12 --user-option");
    expect((await applyManagedLaunch("1", 1, "lsfg", {})).ok).toBe(true);
    expect(state.launch).toBe(original);
  });
  it("refuses a conflicting external configuration without replacing it", async () => {
    state.launch = 'LSFGVK_CONFIG="/external/custom.toml" ' + state.launch;
    const original = state.launch;
    const result = await applyManagedLaunch("1", 1, "lsfg", { env }, { requireComplete: true });
    expect(result.ok).toBe(false);
    expect(state.launch).toBe(original);
    expect(writeLaunchOptions).not.toHaveBeenCalled();
  });
  it("preserves a configuration path edited by the user after activation", async () => {
    await applyManagedLaunch("1", 1, "lsfg", { env }, { requireComplete: true });
    state.launch = state.launch.replace(env.LSFGVK_CONFIG, '"/external/changed.toml"');
    await applyManagedLaunch("1", 1, "lsfg", {});
    expect(state.launch).toContain('LSFGVK_CONFIG="/external/changed.toml"');
    expect(state.launch).not.toContain("LSFGVK_PROFILE");
    expect(state.launch).toContain("gamemoderun %command% -dx12 --user-option");
  });
});
