// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  getHudState: vi.fn(),
  reloadHud: vi.fn(),
  resetHud: vi.fn(),
  setHudConfig: vi.fn(),
}));

import { getHudState, reloadHud, setHudConfig } from "../api";
import { DEFAULT_MODEL, HudState } from "./model";
import { useHud } from "./useHud";

const state = (model = DEFAULT_MODEL): HudState => ({
  supported: false,
  running: false,
  capability: "inactive",
  applyStatus: model.enabled ? "pending" : "disabled",
  model,
  values: {},
  catalog: [],
  presets: {},
});

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
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
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("coalesces edits and persists only the latest complete model", async () => {
    const { result } = renderHook(() => useHud());
    await settle();

    const first = { ...DEFAULT_MODEL, fontSize: 30 };
    const latest = { ...first, offsetX: 12 };
    act(() => result.current.setModel(first));
    act(() => result.current.setModel(latest));
    await act(async () => {
      vi.advanceTimersByTime(250);
      await Promise.resolve();
    });

    expect(setHudConfig).toHaveBeenCalledTimes(1);
    expect(setHudConfig).toHaveBeenCalledWith(latest);
    expect(result.current.state?.model).toEqual(latest);
  });

  it("enables using the latest unsaved style instead of racing a stale debounce", async () => {
    const { result } = renderHook(() => useHud());
    await settle();

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
    const { result } = renderHook(() => useHud());
    await settle();

    act(() => result.current.reload());
    await settle();

    expect(result.current.reloadStatus).toBe("error");
  });

  it("does not let an older poll replace a newer local edit", async () => {
    const oldPoll = deferred<HudState>();
    vi.mocked(getHudState)
      .mockResolvedValueOnce(state())
      .mockReturnValueOnce(oldPoll.promise);
    const { result } = renderHook(() => useHud());
    await settle();

    act(() => vi.advanceTimersByTime(4000));
    const latest = { ...DEFAULT_MODEL, fontSize: 44 };
    act(() => result.current.setModel(latest));
    await act(async () => {
      oldPoll.resolve(state({ ...DEFAULT_MODEL, fontSize: 12 }));
      await Promise.resolve();
    });

    expect(result.current.state?.model).toEqual(latest);
  });

  it("flushes the latest debounced model when the section unmounts", async () => {
    const { result, unmount } = renderHook(() => useHud());
    await settle();

    const latest = { ...DEFAULT_MODEL, fontScale: 1.35 };
    act(() => result.current.setModel(latest));
    act(() => unmount());

    expect(setHudConfig).toHaveBeenCalledWith(latest);
  });
});
