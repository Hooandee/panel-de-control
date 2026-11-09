import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  getEcoState: vi.fn(),
  setEcoScreen: vi.fn(),
  setEco: vi.fn(),
  toast: vi.fn(),
  recordUiEvent: vi.fn(),
  setBrightness: vi.fn(),
  showBlackout: vi.fn((_onTap: () => void) => {}),
  hideBlackout: vi.fn(),
  cancel: vi.fn(),
  started: 0,
  steam: (_active: boolean) => {},
  raw: () => {},
  brightness: (_f: number) => {},
}));

vi.mock("@decky/api", () => ({
  toaster: { toast: h.toast },
  addEventListener: (_e: string, cb: () => void) => (h.raw = cb),
  removeEventListener: () => {},
}));
vi.mock("../api", () => ({ getEcoState: h.getEcoState, setEcoScreen: h.setEcoScreen, setEco: h.setEco }));
vi.mock("./uiEvents", () => ({ recordUiEvent: h.recordUiEvent }));
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
    h.setEco.mockImplementation(async () => {
      const disabled = state({ enabled: false });
      h.getEcoState.mockResolvedValue(disabled);
      return disabled;
    });
    h.getEcoState.mockResolvedValue(state({ enabled: false }));
    h.setEcoScreen.mockResolvedValue({ ok: true, asleep: true });
    stop = startEcoAmbient();
  });

  afterEach(() => {
    stop();
    vi.clearAllMocks();
    vi.useRealTimers();
  });


  it("does not exit on enable, a Steam active state, or one wake tap", async () => {
    enable();
    h.steam(true);
    h.raw();
    await tick(12000);
    expect(h.setEco).not.toHaveBeenCalled();
    expect(h.toast).not.toHaveBeenCalled();
  });

  it.each([true, false])("exits after ten seconds of repeated input (panel=%s)", async (panel) => {
    enable(panel);
    h.raw();
    for (let i = 0; i < 3; i++) {
      await tick(3000);
      h.raw();
    }
    await tick(999);
    expect(h.setEco).not.toHaveBeenCalled();
    await tick(1);
    expect(h.setEco).toHaveBeenCalledExactlyOnceWith(false, 40);
    expect(h.toast).toHaveBeenCalledTimes(1);
    expect(h.recordUiEvent).toHaveBeenCalledWith("system", "eco_auto_exit", { reason: "sustained_activity", source: "wake_input", duration_ms: 10000, input_count: 4, max_gap_ms: 3000 }, true);
    if (!panel) expect(h.setBrightness).toHaveBeenLastCalledWith(0.4);
    await tick(15000);
    expect(h.setEco).toHaveBeenCalledTimes(1);
  });

  it("starts a fresh window after a pause in input", async () => {
    enable();
    h.raw();
    await tick(6000);
    h.raw();
    await tick(3000);
    h.raw();
    await tick(1000);
    expect(h.setEco).not.toHaveBeenCalled();
  });

  it("cancels the activity window on Steam idle and on unload", async () => {
    enable();
    for (let i = 0; i < 3; i++) { h.raw(); await tick(3000); }
    h.steam(false);
    await tick(1000);
    expect(h.setEco).not.toHaveBeenCalled();
    h.raw();
    stop();
    stop = () => {};
    await tick(12000);
    expect(h.setEco).not.toHaveBeenCalled();
  });

  it("does not count time across a suspended or blocked event loop", async () => {
    enable();
    for (let i = 0; i < 3; i++) { h.raw(); await tick(3000); }
    vi.setSystemTime(Date.now() + 60000);
    h.raw();
    await tick(1000);
    expect(h.setEco).not.toHaveBeenCalled();
  });

  it("logs failed exits, keeps Eco active and retries only after renewed sustained input", async () => {
    h.setEco.mockRejectedValueOnce(new Error("unavailable"));
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    expect(h.setEco).toHaveBeenCalledTimes(1);
    expect(h.toast).not.toHaveBeenCalled();
    expect(h.recordUiEvent).toHaveBeenCalledWith("system", "eco_auto_exit", expect.objectContaining({ reason: "sustained_activity", source: "wake_input", duration_ms: 10000 }), false);
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    expect(h.setEco).toHaveBeenCalledTimes(2);
    expect(h.toast).toHaveBeenCalledTimes(1);
  });

  it("does not announce success if the backend still reports Eco enabled", async () => {
    h.setEco.mockResolvedValueOnce(state());
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    expect(h.toast).not.toHaveBeenCalled();
    expect(h.recordUiEvent).toHaveBeenCalledWith("system", "eco_auto_exit", expect.objectContaining({ reason: "sustained_activity", source: "wake_input", duration_ms: 10000 }), false);
  });

  it("ignores a delayed exit response after the user re-enables Eco", async () => {
    let resolve!: (value: unknown) => void;
    h.setEco.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    expect(h.setEco).toHaveBeenCalledTimes(1);
    setEcoActiveHint(false, 40, true);
    enable();
    resolve(state({ enabled: false }));
    await tick(0);
    expect(h.toast).not.toHaveBeenCalled();
    await goIdle();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(true);
  });

  it("does not poll stale enabled state while an exit is pending", async () => {
    let resolve!: (value: unknown) => void;
    h.setEco.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    h.getEcoState.mockClear();
    await tick(3000);
    expect(h.getEcoState).not.toHaveBeenCalled();
    resolve(state({ enabled: false }));
    await tick(0);
  });

  it("resumes polling after an exit timeout and ignores its late response", async () => {
    let resolve!: (value: unknown) => void;
    h.setEco.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    h.getEcoState.mockClear();
    await tick(10000);
    expect(h.toast).not.toHaveBeenCalled();
    expect(h.recordUiEvent).toHaveBeenCalledWith("system", "eco_auto_exit", expect.any(Object), false);
    await tick(3000);
    expect(h.getEcoState).toHaveBeenCalled();
    resolve(state({ enabled: false }));
    await tick(0);
    expect(h.toast).not.toHaveBeenCalled();
  });

  it("ignores an old exit response after unload and restart", async () => {
    let resolve!: (value: unknown) => void;
    h.setEco.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    enable();
    for (let i = 0; i < 4; i++) { h.raw(); await tick(2500); }
    stop();
    stop = startEcoAmbient();
    await tick(0);
    resolve(state({ enabled: false }));
    await tick(0);
    expect(h.toast).not.toHaveBeenCalled();
    await goIdle();
    expect(h.setEcoScreen).toHaveBeenLastCalledWith(true);
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
