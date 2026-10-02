import { afterEach, describe, expect, it, vi } from "vitest";

import { recordUiEvent, setUiEventSink } from "./uiEvents";

afterEach(() => {
  setUiEventSink(null);
  vi.useRealTimers();
});

describe("ui events", () => {
  it("does nothing without a sink", () => {
    expect(() => recordUiEvent("display", "brightness", { fraction: 0.5 })).not.toThrow();
  });

  it("sends a dragged slider once, with its last value", () => {
    vi.useFakeTimers();
    const sent: unknown[][] = [];
    setUiEventSink((...args) => sent.push(args));
    recordUiEvent("display", "brightness", { fraction: 0.2 });
    recordUiEvent("display", "brightness", { fraction: 0.5 });
    recordUiEvent("audio", "steam_volume", { fraction: 0.3 }, false);
    vi.advanceTimersByTime(1100);
    expect(sent).toEqual([
      ["display", "brightness", '{"fraction":0.5}', true],
      ["audio", "steam_volume", '{"fraction":0.3}', false],
    ]);
  });
});
