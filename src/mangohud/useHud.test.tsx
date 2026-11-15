// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  getHudState: vi.fn(),
  reloadHud: vi.fn(),
  resolveHudConflict: vi.fn(),
  resetHud: vi.fn(),
  setHudConfig: vi.fn(),
}));

import { getHudState, reloadHud, resolveHudConflict, setHudConfig } from "../api";
import { DEFAULT_MODEL, HudState } from "./model";
import { useHud, useHudValues } from "./useHud";

const state = (model = DEFAULT_MODEL): HudState => ({
  capability: "inactive",
  applyStatus: model.enabled ? "pending" : "disabled",
  conflict: null,
  model,
  values: {},
});

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function edit(result: { current: ReturnType<typeof useHud> }, model: typeof DEFAULT_MODEL) {
  act(() => result.current.setModel(model));
  await advance(700);
}

async function renderHud() {
  const hook = renderHook(() => useHud());
  await settle();
  return hook;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("useHud coordination", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.mocked(getHudState).mockResolvedValue(state());
    vi.mocked(setHudConfig).mockImplementation(async (model) => state(model));
    vi.mocked(reloadHud).mockResolvedValue(state());
    vi.mocked(resolveHudConflict).mockResolvedValue(state());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("coalesces edits and persists only the latest complete model", async () => {
    const { result } = await renderHud();

    const first = { ...DEFAULT_MODEL, fontSize: 30 };
    const latest = { ...first, offsetX: 12 };
    act(() => result.current.setModel(first));
    await edit(result, latest);

    expect(setHudConfig).toHaveBeenCalledTimes(1);
    expect(setHudConfig).toHaveBeenCalledWith(latest);
    expect(result.current.state?.model).toEqual(latest);
  });

  it("keeps one request in flight and replaces the queued model with the latest edit", async () => {
    const firstRequest = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(firstRequest.promise);
    const { result } = await renderHud();

    const first = { ...DEFAULT_MODEL, fontSize: 30 };
    await edit(result, first);

    const intermediate = { ...first, offsetX: 8 };
    const latest = { ...intermediate, offsetX: 18 };
    act(() => result.current.setModel(intermediate));
    await edit(result, latest);

    expect(setHudConfig).toHaveBeenCalledTimes(1);

    firstRequest.resolve(state(first));
    await settle();

    expect(setHudConfig).toHaveBeenCalledTimes(2);
    expect(setHudConfig).toHaveBeenLastCalledWith(latest);
  });

  it("reports a stalled save without overlapping the underlying RPC", async () => {
    const stalled = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(stalled.promise);
    const { result } = await renderHud();

    const first = { ...DEFAULT_MODEL, fontSize: 30 };
    await edit(result, first);
    const latest = { ...first, offsetX: 18 };
    await edit(result, latest);

    expect(setHudConfig).toHaveBeenCalledTimes(1);
    await advance(4000);

    expect(setHudConfig).toHaveBeenCalledTimes(1);
    expect(result.current.saveStatus).toBe("error");
    expect(result.current.state?.model).toEqual(latest);

    stalled.resolve(state(first));
    await settle();

    expect(setHudConfig).toHaveBeenCalledTimes(2);
    expect(setHudConfig).toHaveBeenLastCalledWith(latest);
  });

  it("does not overlap polls after the visible timeout", async () => {
    const stalled = deferred<HudState>();
    vi.mocked(getHudState).mockReturnValue(stalled.promise);
    await renderHud();

    await advance(12000);

    expect(getHudState).toHaveBeenCalledTimes(1);

    stalled.resolve(state());
    await settle();
    await advance(4000);

    expect(getHudState).toHaveBeenCalledTimes(2);
  });

  it("ignores a stalled save that settles after its timeout", async () => {
    const stalled = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(stalled.promise);
    const { result } = await renderHud();

    const old = { ...DEFAULT_MODEL, fontSize: 20 };
    await edit(result, old);
    await advance(4000);

    const latest = { ...old, fontSize: 44 };
    await edit(result, latest);
    expect(result.current.state?.model).toEqual(latest);

    stalled.resolve(state(old));
    await settle();

    expect(result.current.state?.model).toEqual(latest);
  });

  it("enables using the latest unsaved style instead of racing a stale debounce", async () => {
    const { result } = await renderHud();

    const styled = { ...DEFAULT_MODEL, offsetY: 28 };
    act(() => result.current.setModel(styled));
    act(() => result.current.setEnabled(true));
    await settle();
    act(() => vi.advanceTimersByTime(300));

    expect(setHudConfig).toHaveBeenCalledTimes(1);
    expect(setHudConfig).toHaveBeenCalledWith({ ...styled, enabled: true });
  });

  it("reports a reload failure instead of announcing success", async () => {
    vi.mocked(reloadHud).mockRejectedValueOnce(new Error("reload failed"));
    const { result } = await renderHud();

    act(() => result.current.reload());
    await settle();

    expect(result.current.reloadStatus).toBe("error");
  });

  it("does not overlap manual commands after the visible timeout", async () => {
    const stalled = deferred<HudState>();
    vi.mocked(reloadHud).mockReturnValueOnce(stalled.promise);
    const { result } = await renderHud();

    act(() => result.current.reload());
    await settle();
    await advance(4000);
    act(() => result.current.reload());

    expect(reloadHud).toHaveBeenCalledTimes(1);
    expect(result.current.reloadStatus).toBe("error");

    stalled.resolve(state());
    await settle();
    act(() => result.current.reload());
    await settle();

    expect(reloadHud).toHaveBeenCalledTimes(2);
  });

  it("waits for the latest persistence before reloading MangoHud", async () => {
    const saveRequest = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(saveRequest.promise);
    const { result } = await renderHud();

    const latest = { ...DEFAULT_MODEL, offsetY: 16 };
    await edit(result, latest);
    act(() => result.current.reload());
    await settle();

    expect(reloadHud).not.toHaveBeenCalled();

    saveRequest.resolve(state(latest));
    await settle();

    expect(reloadHud).toHaveBeenCalledTimes(1);
  });

  it("drains a queued save before acquiring the manual command slot", async () => {
    const firstRequest = deferred<HudState>();
    const latestRequest = deferred<HudState>();
    vi.mocked(setHudConfig)
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(latestRequest.promise);
    const { result } = await renderHud();

    const first = { ...DEFAULT_MODEL, fontSize: 30 };
    await edit(result, first);
    const latest = { ...first, offsetX: 18 };
    await edit(result, latest);
    act(() => result.current.reload());

    firstRequest.resolve(state(first));
    await settle();

    expect(setHudConfig).toHaveBeenCalledTimes(2);
    expect(setHudConfig).toHaveBeenLastCalledWith(latest);
    expect(reloadHud).not.toHaveBeenCalled();

    latestRequest.resolve(state(latest));
    await settle();

    expect(reloadHud).toHaveBeenCalledTimes(1);
  });

  it("waits for the latest persistence before resolving an ownership conflict", async () => {
    const saveRequest = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(saveRequest.promise);
    const { result } = await renderHud();

    const latest = { ...DEFAULT_MODEL, offsetY: 16 };
    await edit(result, latest);
    act(() => result.current.resolveConflict("use_pdc"));
    await settle();

    expect(resolveHudConflict).not.toHaveBeenCalled();

    saveRequest.resolve(state(latest));
    await settle();

    expect(resolveHudConflict).toHaveBeenCalledWith("use_pdc");
  });

  it("does not let an older poll replace a newer local edit", async () => {
    const oldPoll = deferred<HudState>();
    vi.mocked(getHudState)
      .mockResolvedValueOnce(state())
      .mockReturnValueOnce(oldPoll.promise);
    const { result } = await renderHud();

    act(() => vi.advanceTimersByTime(4000));
    const latest = { ...DEFAULT_MODEL, fontSize: 44 };
    act(() => result.current.setModel(latest));
    await act(async () => {
      oldPoll.resolve(state({ ...DEFAULT_MODEL, fontSize: 12 }));
      await Promise.resolve();
    });

    expect(result.current.state?.model).toEqual(latest);
  });

  it("publishes live values without replacing the editor state on every poll", async () => {
    const initial = { ...state(), values: { pdc_tdp: "15W" } } as HudState;
    const refreshed = { ...state(), values: { pdc_tdp: "16W" } } as HudState;
    const cleared = state();
    vi.mocked(getHudState)
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(refreshed)
      .mockResolvedValueOnce(cleared);

    const { result } = renderHook(() => ({
      controller: useHud(),
      values: useHudValues(),
    }));
    await settle();
    const editorState = result.current.controller.state;

    await advance(4000);

    expect(result.current.values.pdc_tdp).toBe("16W");
    expect(result.current.controller.state).toBe(editorState);

    await advance(4000);

    expect(result.current.values.pdc_tdp).toBeUndefined();
    expect(result.current.controller.state).toBe(editorState);
  });

  it("still replaces editor state when a control status changes", async () => {
    const initial = state();
    const failed = { ...state(), applyStatus: "failed" } as HudState;
    vi.mocked(getHudState)
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(failed);

    const { result } = await renderHud();
    const editorState = result.current.state;

    await advance(4000);

    expect(result.current.state).not.toBe(editorState);
    expect(result.current.state?.applyStatus).toBe("failed");
  });

  it("flushes the latest debounced model when the section unmounts", async () => {
    const { result, unmount } = await renderHud();

    const latest = { ...DEFAULT_MODEL, fontScale: 1.35 };
    act(() => result.current.setModel(latest));
    act(() => unmount());

    expect(setHudConfig).toHaveBeenCalledWith(latest);
  });

  it("queues the latest unmounted model behind an in-flight request", async () => {
    const firstRequest = deferred<HudState>();
    vi.mocked(setHudConfig).mockReturnValueOnce(firstRequest.promise);
    const { result, unmount } = await renderHud();

    const first = { ...DEFAULT_MODEL, fontScale: 1.1 };
    await edit(result, first);

    const latest = { ...first, fontScale: 1.4 };
    act(() => result.current.setModel(latest));
    act(() => unmount());
    expect(setHudConfig).toHaveBeenCalledTimes(1);

    firstRequest.resolve(state(first));
    await settle();

    expect(setHudConfig).toHaveBeenCalledTimes(2);
    expect(setHudConfig).toHaveBeenLastCalledWith(latest);
  });
});
