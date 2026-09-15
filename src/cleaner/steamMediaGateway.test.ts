// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  recording: {
    GetClipsHandler: { name: "GameRecording.GetClips#1" },
    GetAppsWithBackgroundVideo: vi.fn(),
    GetClips: vi.fn(),
    ManuallyDeleteRecordingsForApps: vi.fn(),
    DeleteClip: vi.fn(),
  },
  measure: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  findModuleByExport: (predicate: (value: unknown) => boolean) => predicate(mocks.recording) ? { service: mocks.recording } : undefined,
}));
vi.mock("../api", () => ({ measureSteamScreenshotPaths: mocks.measure }));

import { createSteamMediaGateway } from "./steamMediaGateway";

const response = (body: object, success = true) => ({
  BSuccess: () => success,
  Body: () => ({ toObject: () => body }),
});

beforeEach(() => {
  vi.resetAllMocks();
  Object.assign(window, {
    SteamClient: {
      Screenshots: {
        GetAllAppsLocalScreenshotsCount: vi.fn().mockResolvedValue(2),
        GetAllAppsLocalScreenshotsRange: vi.fn().mockResolvedValue([{ strGameID: "10", hHandle: 1 }, { strGameID: "20", hHandle: 2 }]),
        GetLocalScreenshotPath: vi.fn().mockResolvedValue("/steam/shot.jpg"),
        DeleteLocalScreenshots: vi.fn().mockResolvedValue({ bSuccess: true, rgFailedRequestIndices: [] }),
      },
    },
  });
  mocks.recording.GetAppsWithBackgroundVideo.mockResolvedValue(response({ apps: [{ game_id: "10" }] }));
  mocks.recording.GetClips.mockResolvedValue(response({ clip: [{ clip_id: "clip" }] }));
  mocks.recording.ManuallyDeleteRecordingsForApps.mockResolvedValue(response({}));
  mocks.recording.DeleteClip.mockResolvedValue(response({}));
  mocks.measure.mockResolvedValue({ "/steam/shot.jpg": 20 });
});

describe("Steam media gateway", () => {
  it("uses Steam's indexed screenshot and recording services", async () => {
    const gateway = createSteamMediaGateway();

    expect(await gateway.listScreenshots()).toHaveLength(2);
    expect(await gateway.listBackgroundRecordings()).toEqual([{ game_id: "10" }]);
    expect(await gateway.listClips()).toEqual([{ clip_id: "clip" }]);
    expect(await gateway.screenshotPath("10", 1)).toBe("/steam/shot.jpg");
    expect(await gateway.measureScreenshotPaths(["/steam/shot.jpg"])).toEqual({ "/steam/shot.jpg": 20 });

    const screenshots = (window as unknown as { SteamClient: { Screenshots: Record<string, ReturnType<typeof vi.fn>> } }).SteamClient.Screenshots;
    expect(screenshots.GetAllAppsLocalScreenshotsRange).toHaveBeenCalledWith(0, 1);
  });

  it("routes every deletion through Steam and checks its result", async () => {
    const gateway = createSteamMediaGateway();

    expect(await gateway.deleteBackgroundRecordings(["10", "20"])).toBe(true);
    expect(await gateway.deleteClip("clip")).toBe(true);
    expect(mocks.recording.ManuallyDeleteRecordingsForApps).toHaveBeenCalledWith({ game_ids: ["10", "20"] });
    expect(mocks.recording.DeleteClip).toHaveBeenCalledWith({ clip_id: "clip" });
  });

  it("preserves invalid screenshot responses for the cleaner to classify", async () => {
    const screenshots = (window as unknown as { SteamClient: { Screenshots: Record<string, ReturnType<typeof vi.fn>> } }).SteamClient.Screenshots;
    screenshots.DeleteLocalScreenshots.mockResolvedValue({ bSuccess: true, rgFailedRequestIndices: null });

    await expect(createSteamMediaGateway().deleteScreenshots([{ gameID: "10", rgHandles: [1] }]))
      .resolves.toEqual({ bSuccess: true, rgFailedRequestIndices: null });
  });

  it("distinguishes an invalid deletion response from a Steam API failure", async () => {
    mocks.recording.DeleteClip.mockResolvedValue({});
    await expect(createSteamMediaGateway().deleteClip("clip")).rejects.toMatchObject({ reason: "invalid_response" });

    mocks.recording.DeleteClip.mockRejectedValue(new Error("private response"));
    await expect(createSteamMediaGateway().deleteClip("clip")).rejects.toMatchObject({ reason: "steam_api_error" });
  });

  it("forwards one bounded screenshot measurement request", async () => {
    const gateway = createSteamMediaGateway();
    const paths = Array.from({ length: 500 }, (_, index) => `/steam/${index}.jpg`);
    mocks.measure.mockImplementation(async (batch: string[]) => Object.fromEntries(batch.map((path) => [path, 20])));

    const measured = await gateway.measureScreenshotPaths(paths);

    expect(mocks.measure).toHaveBeenCalledOnce();
    expect(mocks.measure.mock.calls[0][0]).toHaveLength(500);
    expect(Object.keys(measured)).toHaveLength(500);
  });

  it("reports an unavailable screenshot inventory when Steam omits its API", async () => {
    delete (window as unknown as { SteamClient?: unknown }).SteamClient;
    const gateway = createSteamMediaGateway();

    await expect(gateway.listScreenshots()).rejects.toThrow("media_unavailable");
    expect(await gateway.screenshotPath("10", 1)).toBeNull();
  });

  it("stops requesting screenshot pages after Limpieza closes", async () => {
    const screenshots = (window as unknown as { SteamClient: { Screenshots: Record<string, ReturnType<typeof vi.fn>> } }).SteamClient.Screenshots;
    screenshots.GetAllAppsLocalScreenshotsCount.mockResolvedValue(2_000);
    let active = true;
    screenshots.GetAllAppsLocalScreenshotsRange.mockImplementation(async () => {
      active = false;
      return [];
    });

    await createSteamMediaGateway().listScreenshots(() => active);

    expect(screenshots.GetAllAppsLocalScreenshotsRange).toHaveBeenCalledOnce();
  });

  it("rejects an inventory count it cannot cover completely", async () => {
    const screenshots = (window as unknown as { SteamClient: { Screenshots: Record<string, ReturnType<typeof vi.fn>> } }).SteamClient.Screenshots;
    screenshots.GetAllAppsLocalScreenshotsCount.mockResolvedValue(10_001);

    await expect(createSteamMediaGateway().listScreenshots()).rejects.toThrow("media_unavailable");

    expect(screenshots.GetAllAppsLocalScreenshotsRange).not.toHaveBeenCalled();
  });
});
