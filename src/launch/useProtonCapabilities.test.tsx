// @vitest-environment happy-dom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("../api", () => ({ getProtonCaps: vi.fn() }));
import { getProtonCaps } from "../api";
import { useProtonCapabilities } from "./useProtonCapabilities";
const getCaps = vi.mocked(getProtonCaps);

describe("Proton capability lifecycle", () => {
  beforeEach(() => { getCaps.mockReset(); });
  afterEach(cleanup);
  it("clears old supported flags when switching to an unresolved tool", async () => {
    getCaps.mockResolvedValueOnce({ found: true, envs: ["FSR4_UPGRADE"] });
    const { result, rerender } = renderHook(({ name }) => useProtonCapabilities(name, false), { initialProps: { name: "first" } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    getCaps.mockImplementationOnce(() => new Promise(() => {}));
    rerender({ name: "second" });
    expect(result.current).toEqual({ status: "loading", envs: [] });
  });
  it("ignores a late result from the previous tool", async () => {
    let resolveOld!: (value: { found: boolean; envs: string[] }) => void;
    getCaps.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    getCaps.mockResolvedValueOnce({ found: false, envs: [] });
    const { result, rerender } = renderHook(({ name }) => useProtonCapabilities(name, false), { initialProps: { name: "first" } });
    rerender({ name: "second" });
    await waitFor(() => expect(result.current.status).toBe("missing"));
    await act(async () => resolveOld({ found: true, envs: ["FSR4_UPGRADE"] }));
    expect(result.current.status).toBe("missing");
    expect(result.current.envs).toEqual([]);
  });
  it("does not trust envs when found is false", async () => {
    getCaps.mockResolvedValue({ found: false, envs: ["FSR4_UPGRADE"] });
    const { result } = renderHook(() => useProtonCapabilities("missing", false));
    await waitFor(() => expect(result.current.status).toBe("missing"));
    expect(result.current.envs).toEqual([]);
  });
  it("reports lookup failure without stale capabilities", async () => {
    getCaps.mockImplementation(async () => { throw new Error("offline"); });
    const { result } = renderHook(() => useProtonCapabilities("tool", false));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.envs).toEqual([]);
  });
  it("recovers from an error after selecting a supported tool", async () => {
    getCaps.mockRejectedValueOnce(new Error("offline"));
    const { result, rerender } = renderHook(({ name }) => useProtonCapabilities(name, false), { initialProps: { name: "first" } });
    await waitFor(() => expect(result.current.status).toBe("error"));
    getCaps.mockResolvedValueOnce({ found: true, envs: ["FSR4_UPGRADE"] });
    rerender({ name: "second" });
    expect(result.current.envs).toEqual([]);
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.envs).toEqual(["FSR4_UPGRADE"]);
  });

});
