// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mock the effectful edges so the real hook logic (compose + pending/flush) runs
// against controllable Steam reads/writes.
const writes: Array<{ appid: number; value: string }> = [];
let currentLaunch = "";

vi.mock("./steamApi", () => ({
  readAppDetails: vi.fn(async () => ({ launch: currentLaunch, compatName: "", compatDisplay: "" })),
  writeLaunchOptions: vi.fn((appid: number, value: string) => {
    writes.push({ appid, value });
    currentLaunch = value;
    return true;
  }),
}));
vi.mock("../api", () => ({
  getLaunchUsage: vi.fn(async () => ({})),
  bumpLaunchUsage: vi.fn(async () => undefined),
}));
vi.mock("@decky/api", () => ({ toaster: { toast: vi.fn() } }));
vi.mock("../i18n", () => ({ translate: (k: string) => k }));

import { useLaunchEditor } from "./useLaunchEditor";
import { GameEntry } from "./steamApi";

const GAME: GameEntry = {
  liveAppid: 4242,
  stableKey: "4242",
  instanceKey: "4242",
  name: "Test Game",
  isNonSteam: false,
  coverUrls: [],
  lastPlayed: 0,
  playtime: 0,
};

// Let the mounted readAppDetails promise resolve and its state settle.
async function settleBaseline() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useLaunchEditor autosave / flush", () => {
  beforeEach(() => {
    writes.length = 0;
    currentLaunch = "";
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("enable then disable within the debounce, then close, writes nothing stale (issue #272)", async () => {
    const { result, unmount } = renderHook(() => useLaunchEditor(GAME));
    await settleBaseline();
    expect(result.current.loading).toBe(false);

    // Toggle a wrapper on, then off, both well inside the 500ms debounce window.
    act(() => result.current.set("mangohud", true));
    expect(result.current.preview).toBe("mangohud %command%");
    act(() => {
      vi.advanceTimersByTime(150);
    });
    act(() => result.current.set("mangohud", false));
    expect(result.current.preview).toBe("");

    // Close the editor before the debounce fires → the unmount flush runs.
    act(() => {
      unmount();
    });

    // The bug: the flush wrote back the stale "mangohud %command%" the user turned
    // off. It must never write that, and here (net no change) it writes nothing.
    expect(writes.some((w) => w.value === "mangohud %command%")).toBe(false);
    expect(currentLaunch).toBe("");
  });

  it("enable then close before the debounce still persists the intended change", async () => {
    const { result, unmount } = renderHook(() => useLaunchEditor(GAME));
    await settleBaseline();

    act(() => result.current.set("mangohud", true));
    act(() => {
      vi.advanceTimersByTime(150);
    });
    act(() => {
      unmount();
    });

    expect(currentLaunch).toBe("mangohud %command%");
  });

  it("disabling the last option clears the launch string on save", async () => {
    currentLaunch = "mangohud %command%";
    const { result } = renderHook(() => useLaunchEditor(GAME));
    await settleBaseline();
    expect(result.current.selections.mangohud).toBe(true);

    act(() => result.current.set("mangohud", false));
    await act(async () => {
      vi.advanceTimersByTime(600);
      await Promise.resolve();
    });

    expect(currentLaunch).toBe("");
  });
});
