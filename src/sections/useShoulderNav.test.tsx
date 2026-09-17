// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useShoulderNav } from "./useShoulderNav";

type ControllerInputCallback = (
  controllerIndex: number,
  gamepadButton: number,
  isButtonPressed: boolean,
) => void;

interface ControllerRegistration {
  unregister(): void;
}

interface InputBoundary {
  RegisterForControllerInputMessages(callback: ControllerInputCallback): ControllerRegistration;
}

const input = vi.hoisted(() => ({
  callback: null as ControllerInputCallback | null,
  register: vi.fn(),
  unregister: vi.fn(),
}));

function installSteamInput(value: InputBoundary | undefined): void {
  Object.defineProperty(globalThis, "SteamClient", {
    configurable: true,
    value: value ? { Input: value } : undefined,
  });
}

describe("useShoulderNav", () => {
  beforeEach(() => {
    input.callback = null;
    input.register.mockReset();
    input.unregister.mockReset();
    input.register.mockImplementation((callback: ControllerInputCallback): ControllerRegistration => {
      input.callback = callback;
      return { unregister: input.unregister };
    });
    installSteamInput({ RegisterForControllerInputMessages: input.register });
  });

  afterEach(() => {
    cleanup();
    Reflect.deleteProperty(globalThis, "SteamClient");
  });

  it("registers once across mode and section changes", () => {
    const select = vi.fn();
    const { rerender, unmount } = renderHook(
      ({ ids, active }: { ids: string[]; active: string }) => useShoulderNav(ids, active, select),
      { initialProps: { ids: [] as string[], active: "power" } },
    );

    rerender({ ids: ["power", "system"], active: "power" });
    rerender({ ids: ["power", "system"], active: "system" });

    expect(input.register).toHaveBeenCalledOnce();
    unmount();
    expect(input.unregister).toHaveBeenCalledOnce();
  });

  it("ignores an empty list and wraps active lists with L1 and R1", () => {
    const select = vi.fn();
    const { rerender } = renderHook(
      ({ ids, active }: { ids: string[]; active: string }) => useShoulderNav(ids, active, select),
      { initialProps: { ids: [] as string[], active: "power" } },
    );

    act(() => input.callback?.(0, 31, true));
    expect(select).not.toHaveBeenCalled();

    rerender({ ids: ["power", "system"], active: "power" });
    act(() => input.callback?.(0, 30, true));
    expect(select).toHaveBeenLastCalledWith("system");

    rerender({ ids: ["power", "system"], active: "system" });
    act(() => input.callback?.(0, 31, true));
    expect(select).toHaveBeenLastCalledWith("power");
  });

  it("ignores releases and unrelated controller buttons", () => {
    const select = vi.fn();
    renderHook(() => useShoulderNav(["power", "system"], "power", select));

    act(() => input.callback?.(0, 31, false));
    act(() => input.callback?.(0, 1, true));

    expect(select).not.toHaveBeenCalled();
  });

  it("does not throw when Steam input is absent", () => {
    installSteamInput(undefined);

    expect(() => renderHook(() => useShoulderNav(["power"], "power", vi.fn()))).not.toThrow();
  });

  it("does not propagate registration failures", () => {
    input.register.mockImplementation(() => {
      throw new Error("input unavailable");
    });

    expect(() => renderHook(() => useShoulderNav(["power"], "power", vi.fn()))).not.toThrow();
  });
});
