// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  readString: (key: string) => localStorage.getItem(key),
  writeString: (key: string, value: string) => localStorage.setItem(key, value),
}));

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
});

describe("shell mode", () => {
  it.each(["home", "detail", "tabs"] as const)("restores %s", async (mode) => {
    localStorage.setItem("pdc:shellMode", mode);
    const { getShellMode } = await import("./shellMode");
    expect(getShellMode()).toBe(mode);
  });

  it("rejects an unknown mode", async () => {
    localStorage.setItem("pdc:shellMode", "broken");
    const { getShellMode } = await import("./shellMode");
    expect(getShellMode()).toBeNull();
  });

  it("updates the React binding when the mode changes", async () => {
    const { setShellMode, useShellMode } = await import("./shellMode");
    const { result } = renderHook(() => useShellMode());

    expect(result.current).toBeNull();
    act(() => setShellMode("detail"));
    expect(result.current).toBe("detail");
  });
});
