// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";
import { beginThemeObservation, configureThemeInteractionJournal } from "./themeInteractionJournal";

afterEach(() => vi.restoreAllMocks());

it("records a delivered Steam button and the subsequent focus readback once without consuming input", () => {
  const frames = new Map<number, FrameRequestCallback>();
  let next = 0;
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => { frames.set(++next, cb); return next; });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => { frames.delete(id); });
  const button = document.createElement("button");
  document.body.appendChild(button);
  const entries: Record<string, unknown>[] = [];
  const stop = configureThemeInteractionJournal(() => [{ doc: document, surface: "main" }], async (_area, _action, detail) => {
    entries.push(JSON.parse(detail));
  });
  try {
    const complete = beginThemeObservation("installing")!;
    const press = () => button.dispatchEvent(new CustomEvent("vgp_onbuttondown", { bubbles: true, cancelable: true }));
    press();
    complete(true);
    frames.get(1)!(0);
    button.addEventListener("vgp_onbuttondown", () => button.focus(), { once: true });
    expect(press()).toBe(true);
    press();
    frames.get(2)!(1);
    press();
    expect(entries.map((entry) => entry.phase)).toEqual(["started", "completed", "frame", "input", "input_frame"]);
    expect(entries[4]).toMatchObject({ attempt: 1, operation: "installing", surface: "main", focusChanged: true });
    expect(frames.size).toBe(0);
  } finally {
    stop();
    button.remove();
  }
});

it("drops observers on expiry, replacement and dismount, including a late operation result", () => {
  vi.useFakeTimers();
  const phases: string[] = [];
  const stop = configureThemeInteractionJournal(() => [{ doc: document, surface: "qam" }], async (_area, _action, detail) => {
    phases.push(JSON.parse(detail).phase);
  });
  try {
    beginThemeObservation("activating")!(true);
    vi.advanceTimersByTime(120_001);
    document.dispatchEvent(new Event("vgp_onbuttondown"));
    const previous = beginThemeObservation("installing")!;
    const late = beginThemeObservation("activating")!;
    previous(true);
    late(false);
    const pending = beginThemeObservation("installing")!;
    stop();
    pending(true);
    expect(phases.filter((p) => p === "completed")).toHaveLength(1);
    expect(phases).toContain("failed");
    expect(phases).toContain("expired");
    expect(phases).not.toContain("input");
  } finally {
    stop();
    vi.useRealTimers();
  }
});
