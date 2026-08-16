// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AudioState } from "../api";

const mocks = vi.hoisted(() => ({
  getAudioState: vi.fn(),
}));

vi.mock("../api", () => ({
  getAudioState: mocks.getAudioState,
  applyAudioPreset: vi.fn(),
  applyAudioProfile: vi.fn(),
  deleteAudioProfile: vi.fn(),
  resetAudio: vi.fn(),
  saveAudioProfile: vi.fn(),
  setAudioBalance: vi.fn(),
  setAudioBands: vi.fn(),
  setAudioCurve: vi.fn(),
  setAudioEnabled: vi.fn(),
  setAudioFollowGlobal: vi.fn(),
  setAudioLoudness: vi.fn(),
  setAudioTest: vi.fn(),
  setSpeakerGuard: vi.fn(),
}));

vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => null }));
vi.mock("../useScopeSync", () => ({
  useScopeSync: () => ({ scope: "global", onScope: vi.fn() }),
}));

import { useEq } from "./useEq";

const audioState = (route: AudioState["route"]): AudioState => ({
  supported: true,
  enabled: true,
  active: true,
  last_apply: { ok: true },
  route,
  appid: null,
  follows_global: true,
  has_game_profile: false,
  preset: "flat",
  gains: Array(10).fill(0),
  bass: 0,
  loudness: false,
  balance: 0,
  test_playing: false,
  test_sample: null,
  test_samples: [],
  presets: [],
  profiles: [],
  device_name: "Test",
  guard: true,
  safe_limits: { bands: Array(10).fill(12), bass: 100 },
});

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useEq route refresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.getAudioState
      .mockResolvedValueOnce(audioState("speaker"))
      .mockResolvedValue(audioState("headphone"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("refreshes an enabled EQ while the panel remains open", async () => {
    const { result } = renderHook(() => useEq());
    await settle();
    expect(result.current.state?.route).toBe("speaker");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });

    expect(result.current.state?.route).toBe("headphone");
    expect(mocks.getAudioState).toHaveBeenCalledTimes(2);
  });
});
