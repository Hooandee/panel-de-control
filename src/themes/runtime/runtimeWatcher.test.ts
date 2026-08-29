import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "../cssLoaderTypes";
import { startThemeRuntimeWatcher } from "./runtimeWatcher";

describe("startThemeRuntimeWatcher", () => {
  it("does not overlap inspections and ignores a result after disposal", async () => {
    let resolve!: (snapshot: CssLoaderSnapshot) => void;
    const inspect = vi.fn(() => new Promise<CssLoaderSnapshot>((done) => { resolve = done; }));
    const reconcile = vi.fn();
    const watcher = startThemeRuntimeWatcher({
      inspect,
      reconcile,
      intervalMs: 20,
      setInterval: (callback) => {
        callback();
        callback();
        return 1;
      },
      clearInterval: vi.fn(),
    });

    expect(inspect).toHaveBeenCalledOnce();
    watcher.dispose();
    resolve({ status: "ready", backendVersion: 9, themes: [] });
    await Promise.resolve();
    await Promise.resolve();

    expect(reconcile).not.toHaveBeenCalled();
  });

  it("refreshes immediately from a theme-change signal and uses a relaxed fallback", async () => {
    const signalTarget = new EventTarget();
    const inspect = vi.fn(async (): Promise<CssLoaderSnapshot> => ({
      status: "ready",
      backendVersion: 9,
      themes: [],
    }));
    const reconcile = vi.fn();
    const schedule = vi.fn(() => 7);
    const cancel = vi.fn();
    const watcher = startThemeRuntimeWatcher({
      inspect,
      reconcile,
      eventTarget: signalTarget,
      eventName: "pdc:themes-changed",
      setInterval: schedule,
      clearInterval: cancel,
    });
    await Promise.resolve();
    await Promise.resolve();

    expect(schedule).toHaveBeenCalledWith(expect.any(Function), 30_000);
    signalTarget.dispatchEvent(new Event("pdc:themes-changed"));
    await Promise.resolve();
    await Promise.resolve();
    expect(inspect).toHaveBeenCalledTimes(2);

    watcher.dispose();
    signalTarget.dispatchEvent(new Event("pdc:themes-changed"));
    expect(inspect).toHaveBeenCalledTimes(2);
    expect(cancel).toHaveBeenCalledWith(7);
  });
});
