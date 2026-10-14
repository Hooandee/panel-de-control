import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getEcoState: vi.fn(),
  setEcoScreen: vi.fn(),
}));
const activity = vi.hoisted(() => ({ emit: (_active: boolean) => {} }));
const backend = vi.hoisted(() => ({ emit: (_active: boolean) => {} }));
const brightness = vi.hoisted(() => ({ set: vi.fn() }));
const blackout = vi.hoisted(() => ({ showBlackout: vi.fn((_onTap?: () => void) => true), hideBlackout: vi.fn() }));
const countdown = vi.hoisted(() => ({ cancel: vi.fn(), started: 0 }));

vi.mock("@decky/api", () => ({
  addEventListener: (_event: string, cb: (active: boolean) => void) => {
    backend.emit = cb;
  },
  removeEventListener: () => {},
}));
vi.mock("../api", () => api);
vi.mock("../i18n", () => ({ translate: (key: string) => key }));
vi.mock("./ecoBlackout", () => blackout);
vi.mock("./ecoCountdown", () => ({
  startCountdown: (seconds: number, _label: string, onDone: () => void) => {
    countdown.started += 1;
    const timer = setTimeout(onDone, seconds * 1000);
    return {
      cancel: () => {
        countdown.cancel();
        clearTimeout(timer);
      },
    };
  },
}));
vi.mock("./activity", () => ({
  subscribeActive: (cb: (active: boolean) => void) => {
    activity.emit = cb;
    return () => {};
  },
}));
vi.mock("./display", () => ({
  displayBrightness: { set: brightness.set, subscribe: () => () => {} },
}));

import { setEcoActiveHint, startEcoAmbient } from "./ecoAmbient";

function enable(wake: number, screenOff: boolean, extra: Record<string, unknown> = {}) {
  api.getEcoState.mockResolvedValue({ enabled: true, wake_brightness: wake, screen_off: screenOff, ...extra });
  setEcoActiveHint(true, wake, screenOff);
}

async function idle() {
  activity.emit(false);
  await vi.advanceTimersByTimeAsync(800);
}

async function active() {
  activity.emit(true);
  await vi.advanceTimersByTimeAsync(150);
}

describe("download mode screen", () => {
  let stop: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    countdown.started = 0;
    api.getEcoState.mockResolvedValue({ enabled: false, wake_brightness: 40, screen_off: true });
    api.setEcoScreen.mockResolvedValue({ ok: true, asleep: true });
    stop = startEcoAmbient();
  });

  afterEach(() => {
    stop();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("counts down on idle, then switches the panel off; activity lights it", async () => {
    enable(40, true);
    expect(api.setEcoScreen).not.toHaveBeenCalled();
    await idle();
    expect(countdown.started).toBe(1);
    expect(api.setEcoScreen).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.setEcoScreen).toHaveBeenLastCalledWith(true);
    expect(blackout.showBlackout).toHaveBeenCalled();
    await active();
    expect(api.setEcoScreen).toHaveBeenLastCalledWith(false);
    expect(blackout.hideBlackout).toHaveBeenCalled();
    expect(brightness.set).not.toHaveBeenCalled();
  });

  it("activity during the countdown keeps the panel on", async () => {
    enable(40, true);
    await idle();
    await active();
    await vi.advanceTimersByTimeAsync(5000);
    expect(countdown.cancel).toHaveBeenCalled();
    expect(api.setEcoScreen).not.toHaveBeenCalledWith(true);
  });

  it("a backend wake lifts the catch layer and goes dark again if Steam never reports input", async () => {
    enable(40, true);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    blackout.hideBlackout.mockClear();
    backend.emit(true);
    expect(blackout.hideBlackout).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(8000);
    expect(countdown.started).toBe(2);
  });

  it("a backend wake followed by Steam activity follows Steam's idle again", async () => {
    enable(40, true);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    backend.emit(true);
    await active();
    await vi.advanceTimersByTimeAsync(8000);
    expect(countdown.started).toBe(1);
  });

  it("a lit panel never keeps the catch layer", async () => {
    enable(40, true, { screen_asleep: false });
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    expect(blackout.showBlackout).toHaveBeenCalled();
    backend.emit(true);
    blackout.hideBlackout.mockClear();
    backend.emit(true);
    expect(blackout.hideBlackout).toHaveBeenCalled();
    blackout.hideBlackout.mockClear();
    await vi.advanceTimersByTimeAsync(3000);
    expect(blackout.hideBlackout).toHaveBeenCalled();
  });

  it("a tap on the black layer brings the screen back", async () => {
    enable(40, true);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    const calls = blackout.showBlackout.mock.calls;
    const onTap = calls[calls.length - 1][0] as () => void;
    onTap();
    expect(api.setEcoScreen).toHaveBeenLastCalledWith(false);
    expect(blackout.hideBlackout).toHaveBeenCalled();
  });

  it("raw input cancels the countdown at once; only Steam starts it", async () => {
    enable(40, true);
    backend.emit(false);
    expect(countdown.started).toBe(0);
    await idle();
    expect(countdown.started).toBe(1);
    backend.emit(true);
    expect(countdown.cancel).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5000);
    expect(api.setEcoScreen).not.toHaveBeenCalledWith(true);
  });

  it("falls back to black layer and minimum brightness when the panel is not confirmed off", async () => {
    api.setEcoScreen.mockResolvedValue({ ok: false, asleep: false });
    enable(40, true);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    expect(brightness.set).toHaveBeenLastCalledWith(0);
    await active();
    expect(brightness.set).toHaveBeenLastCalledWith(0.4);
  });

  it("uses the black layer directly where gamescope cannot switch the panel", async () => {
    enable(55, false);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.setEcoScreen).not.toHaveBeenCalled();
    expect(blackout.showBlackout).toHaveBeenCalled();
    expect(brightness.set).toHaveBeenLastCalledWith(0);
  });

  it("leaves the screen lit when download mode ends while dark", async () => {
    enable(40, true);
    await idle();
    await vi.advanceTimersByTimeAsync(3000);
    api.getEcoState.mockResolvedValue({ enabled: false, wake_brightness: 40, screen_off: true });
    setEcoActiveHint(false, 40, true);
    expect(api.setEcoScreen).toHaveBeenLastCalledWith(false);
    expect(blackout.hideBlackout).toHaveBeenCalled();
  });
});
