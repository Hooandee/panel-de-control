import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  getEcoState: vi.fn(),
  setEcoScreen: vi.fn(),
  setBrightness: vi.fn(),
  showBlackout: vi.fn((_onTap?: () => void) => true),
  hideBlackout: vi.fn(),
  cancel: vi.fn(),
  started: 0,
  steam: (_active: boolean) => {},
  raw: () => {},
  brightness: (_f: number) => {},
}));

vi.mock("@decky/api", () => ({
  addEventListener: (_e: string, cb: () => void) => (h.raw = cb),
  removeEventListener: () => {},
}));
vi.mock("../api", () => ({ getEcoState: h.getEcoState, setEcoScreen: h.setEcoScreen }));
vi.mock("../i18n", () => ({ translate: (k: string) => k }));
vi.mock("./ecoBlackout", () => ({ showBlackout: h.showBlackout, hideBlackout: h.hideBlackout }));
vi.mock("./ecoCountdown", () => ({
  startCountdown: (s: number, _l: string, done: () => void) => {
    h.started += 1;
    const t = setTimeout(done, s * 1000);
    return () => {
      h.cancel();
      clearTimeout(t);
    };
  },
}));
vi.mock("./activity", () => ({ subscribeActive: (cb: (a: boolean) => void) => ((h.steam = cb), () => {}) }));
vi.mock("./display", () => ({
  displayBrightness: { set: h.setBrightness, subscribe: (cb: (f: number) => void) => ((h.brightness = cb), () => {}) },
}));

import { setEcoActiveHint, startEcoAmbient } from "./ecoAmbient";

const state = (extra: Record<string, unknown> = {}) => ({
  enabled: true, wake_brightness: 40, screen_off: true, screen_asleep: false, ...extra,
});

function enable(screenOff = true, extra: Record<string, unknown> = {}) {
  h.getEcoState.mockResolvedValue(state({ screen_off: screenOff, ...extra }));
  setEcoActiveHint(true, 40, screenOff);
}

const tick = (ms: number) => vi.advanceTimersByTimeAsync(ms);
async function goIdle() {
  h.steam(false);
  await tick(3000);
}

describe("download mode screen", () => {
  let stop: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    h.started = 0;
    h.getEcoState.mockResolvedValue(state({ enabled: false }));
    h.setEcoScreen.mockResolvedValue({ ok: true, asleep: true });
    stop = startEcoAmbient();
  });

  afterEach(() => {
    stop();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("counts down on Steam idle, then sleeps the panel; Steam activity wakes it", async () => {
    enable();
    h.raw();
    expect(h.started).toBe(0);
    await goIdle();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(true);
    expect(h.showBlackout).toHaveBeenCalled();
    h.steam(true);
    await tick(150);
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(false);
    expect(h.hideBlackout).toHaveBeenCalled();
    expect(h.setBrightness).not.toHaveBeenCalled();
  });

  it("any activity during the countdown keeps the screen on", async () => {
    enable();
    h.steam(false);
    await tick(0);
    h.raw();
    await tick(5000);
    expect(h.cancel).toHaveBeenCalled();
    expect(h.setEcoScreen).not.toHaveBeenCalledWith(true);
  });

  it("raw input wakes at once, and goes dark again if Steam never reports it", async () => {
    enable();
    await goIdle();
    h.raw();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(false);
    await tick(8000);
    expect(h.started).toBe(2);
  });

  it("raw input Steam does not count keeps the screen on while it continues", async () => {
    enable();
    await goIdle();
    h.raw();
    for (let i = 0; i < 4; i++) {
      await tick(5000);
      h.raw();
    }
    expect(h.started).toBe(1);
  });

  it("a tap on the black layer wakes the screen", async () => {
    enable();
    await goIdle();
    h.showBlackout.mock.calls[h.showBlackout.mock.calls.length - 1][0]!();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(false);
  });

  it("falls back to black layer at minimum brightness when the panel is not confirmed off", async () => {
    h.setEcoScreen.mockResolvedValue({ ok: false, asleep: false });
    enable();
    await goIdle();
    expect(h.setBrightness).toHaveBeenLastCalledWith(0);
    h.steam(true);
    await tick(150);
    expect(h.setBrightness).toHaveBeenLastCalledWith(0.4);
  });

  it("uses the black layer where gamescope cannot switch the panel, keeping a low pick", async () => {
    enable(false);
    await tick(2500);
    h.brightness(0.01);
    await goIdle();
    expect(h.setEcoScreen).not.toHaveBeenCalled();
    expect(h.setBrightness).toHaveBeenLastCalledWith(0);
    h.steam(true);
    await tick(150);
    expect(h.setBrightness).toHaveBeenLastCalledWith(0.01);
  });

  it("switches to panel power once it becomes available", async () => {
    enable(false);
    h.getEcoState.mockResolvedValue(state());
    await tick(3000);
    await goIdle();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(true);
  });

  it("a lit panel never keeps the catch layer or stays asleep, whatever was missed", async () => {
    enable(true, { screen_asleep: true });
    await tick(3000);
    expect(h.hideBlackout).toHaveBeenCalled();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(false);
  });

  it("a session picked up after a reload starts lit", async () => {
    stop();
    h.getEcoState.mockResolvedValue(state({ screen_off: false }));
    stop = startEcoAmbient();
    await tick(0);
    expect(h.setBrightness).toHaveBeenLastCalledWith(0.4);
  });

  it("leaving download mode while dark restores the screen", async () => {
    enable();
    await goIdle();
    setEcoActiveHint(false, 40, true);
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(false);
    expect(h.hideBlackout).toHaveBeenCalled();
  });

  it("a poll answered after unload does not revive the controller", async () => {
    let answer: (s: unknown) => void = () => {};
    enable();
    h.getEcoState.mockReturnValue(new Promise((r) => (answer = r)));
    await tick(3000);
    stop();
    stop = () => {};
    answer(state());
    await goIdle();
    expect(h.started).toBe(0);
  });
});
