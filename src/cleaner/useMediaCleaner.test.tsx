// @vitest-environment happy-dom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MediaGateway } from "./media";

const mocks = vi.hoisted(() => ({ gateway: {} as MediaGateway }));
vi.mock("./steamMediaGateway", () => ({ createSteamMediaGateway: () => mocks.gateway }));
const diagnostics = vi.hoisted(() => ({ record: vi.fn().mockResolvedValue(true) }));
vi.mock("../api", () => ({ recordSteamMediaEvent: diagnostics.record }));
import { useMediaCleaner } from "./useMediaCleaner";

const screenshot = { strGameID: "10", hHandle: 7, nCreated: 1, nWidth: 1280, nHeight: 800, strUrl: "shot.jpg" };
const operationId = expect.stringMatching(/^(?:[a-f0-9]{4}-){7}[a-f0-9]{4}$/);

beforeEach(() => {
  diagnostics.record.mockReset().mockResolvedValue(true);
  mocks.gateway = {
    listScreenshots: vi.fn().mockResolvedValue([screenshot]),
    screenshotPath: vi.fn().mockResolvedValue("/steam/shot.jpg"),
    measureScreenshotPaths: vi.fn().mockResolvedValue({ "/steam/shot.jpg": 50 }),
    listBackgroundRecordings: vi.fn().mockResolvedValue([]),
    listClips: vi.fn().mockResolvedValue([]),
    deleteScreenshots: vi.fn().mockResolvedValue({ bSuccess: true, rgFailedRequestIndices: [] }),
    deleteBackgroundRecordings: vi.fn().mockResolvedValue(true),
    deleteClip: vi.fn().mockResolvedValue(true),
  };
});
afterEach(cleanup);

describe("media cleaner controller", () => {
  it("scans once on mount and publishes the measured item", async () => {
    const { result } = renderHook(useMediaCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].bytes).toBe(50);
    expect(mocks.gateway.listScreenshots).toHaveBeenCalledOnce();
    expect(diagnostics.record).toHaveBeenCalledWith("scan_completed", operationId, 1, 0, "none", "none");
  });

  it("keeps analysis and cleanup responsive while diagnostics are pending", async () => {
    diagnostics.record.mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(useMediaCleaner);

    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.clean(["screenshot:10:7"]));

    expect(mocks.gateway.deleteScreenshots).toHaveBeenCalledOnce();
    expect(result.current.result?.bytesRemoved).toBe(50);
  });

  it("cleans only explicit ids and lets the result be dismissed", async () => {
    const { result } = renderHook(useMediaCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.clean(["screenshot:10:7"]));
    expect(result.current.items).toEqual([]);
    expect(result.current.result?.bytesRemoved).toBe(50);
    expect(diagnostics.record).toHaveBeenCalledWith("cleanup_completed", operationId, 1, 0, "none", "none");
    act(() => result.current.dismissResult());
    expect(result.current.result).toBeNull();
  });

  it("ignores late results after leaving Limpieza", async () => {
    let finish!: (value: typeof screenshot[]) => void;
    mocks.gateway.listScreenshots = vi.fn().mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const { result, unmount } = renderHook(useMediaCleaner);
    expect(result.current.loading).toBe(true);
    unmount();
    await act(async () => { finish([screenshot]); });
    expect(mocks.gateway.measureScreenshotPaths).not.toHaveBeenCalled();
  });

  it("dismisses the previous result as soon as another cleanup starts", async () => {
    mocks.gateway.deleteScreenshots = vi.fn().mockResolvedValue({ bSuccess: false, rgFailedRequestIndices: [0] });
    const { result } = renderHook(useMediaCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.clean(["screenshot:10:7"]));
    expect(result.current.result).not.toBeNull();
    expect(diagnostics.record).toHaveBeenCalledWith("cleanup_failed", operationId, 1, 1, "screenshots", "steam_rejected");

    const calls = diagnostics.record.mock.calls.filter(([event]) => event.startsWith("cleanup_"));
    expect(new Set(calls.map(([, id]) => id))).toHaveLength(1);

    let finish!: (value: { bSuccess: boolean; rgFailedRequestIndices: number[] }) => void;
    mocks.gateway.deleteScreenshots = vi.fn().mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    act(() => { void result.current.clean(["screenshot:10:7"]); });

    expect(result.current.result).toBeNull();
    await act(async () => { finish({ bSuccess: true, rgFailedRequestIndices: [] }); });
  });

  it("does not start a cleanup while a new analysis is running", async () => {
    const { result } = renderHook(useMediaCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    mocks.gateway.listScreenshots = vi.fn().mockReturnValue(new Promise(() => undefined));
    act(() => { void result.current.scan(); });
    await waitFor(() => expect(result.current.loading).toBe(true));

    await act(() => result.current.clean(["screenshot:10:7"]));

    expect(mocks.gateway.deleteScreenshots).not.toHaveBeenCalled();
  });

  it("clears stale totals when every Steam inventory becomes unavailable", async () => {
    const { result } = renderHook(useMediaCleaner);
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    mocks.gateway.listScreenshots = vi.fn().mockRejectedValue(new Error("unavailable"));
    mocks.gateway.listBackgroundRecordings = vi.fn().mockRejectedValue(new Error("unavailable"));
    mocks.gateway.listClips = vi.fn().mockRejectedValue(new Error("unavailable"));

    await act(() => result.current.scan());

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBe("media_unavailable");
  });
});
