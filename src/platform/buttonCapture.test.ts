import { describe, expect, it, vi } from "vitest";

import { captureButtons } from "./buttonCapture";

describe("captureButtons", () => {
  it("registers each button, consumes it and releases everything", () => {
    const handlers = new Map<number, (e?: unknown) => boolean>();
    const released: number[] = [];
    const tree = {
      RegisterGlobalButtonHandler: (button: number, handler: (e?: unknown) => boolean) => {
        handlers.set(button, handler);
        return () => released.push(button);
      },
    };
    const seen: number[] = [];
    const stop = captureButtons([1, 2], (b) => seen.push(b), () => ({ GetActiveNavTree: () => tree }), () => () => undefined);
    const event = { preventDefault: vi.fn(), stopPropagation: vi.fn() };
    expect(handlers.get(1)?.(event)).toBe(true);
    expect(event.preventDefault).toHaveBeenCalled();
    expect(seen).toEqual([1]);
    stop();
    expect(released).toEqual([2, 1]);
  });

  it("does nothing without a navigation tree", () => {
    expect(() => captureButtons([1], () => undefined, () => null, () => () => undefined)()).not.toThrow();
  });

  it("moves to the tree Steam activates after the QAM closes and releases the old one", () => {
    const makeTree = (name: string, log: string[]) => ({
      handlers: new Map<number, (e?: unknown) => boolean>(),
      RegisterGlobalButtonHandler(button: number, handler: (e?: unknown) => boolean) {
        this.handlers.set(button, handler);
        return () => log.push(`${name}-${button}`);
      },
    });
    const released: string[] = [];
    const qam = makeTree("qam", released);
    const home = makeTree("home", released);
    let active: typeof qam = qam;
    let tick: () => void = () => undefined;
    const seen: number[] = [];
    const stop = captureButtons([1], (b) => seen.push(b), () => ({ GetActiveNavTree: () => active }), (fn) => { tick = fn; return () => { tick = () => undefined; }; });
    active = home;
    tick();
    expect(released).toEqual(["qam-1"]);
    home.handlers.get(1)?.({});
    expect(seen).toEqual([1]);
    tick();
    expect(home.handlers.size).toBe(1);
    stop();
    expect(released).toEqual(["qam-1", "home-1"]);
  });

  it("holds every button but Steam and QAM ahead of the focused element when Steam allows a catch-all", () => {
    const callbacks: Array<(button: number, down: boolean, repeat: boolean) => boolean> = [];
    let unregistered = false;
    const controller = {
      GetActiveNavTree: () => { throw new Error("tree must not be used"); },
      SetCatchAllGamepadInput: (callback: (button: number, down: boolean, repeat: boolean) => boolean) => {
        callbacks.push(callback);
        return { Unregister: () => { unregistered = true; } };
      },
    };
    const seen: number[] = [];
    const stop = captureButtons([1, 9], (b) => seen.push(b), () => controller, () => () => undefined);
    const press = callbacks[0];
    expect(press(1, true, false)).toBe(true);
    expect(press(1, false, false)).toBe(true);
    expect(press(9, true, true)).toBe(true);
    expect(press(4, true, false)).toBe(true);
    expect(press(27, true, false)).toBe(false);
    expect(press(28, true, false)).toBe(false);
    expect(seen).toEqual([1]);
    stop();
    expect(unregistered).toBe(true);
  });
});
