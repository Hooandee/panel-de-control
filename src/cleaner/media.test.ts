import { describe, expect, it, vi } from "vitest";
import { cleanMedia, scanMedia, type MediaGateway } from "./media";

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

function gateway(overrides: Partial<MediaGateway> = {}): MediaGateway {
  return {
    listScreenshots: vi.fn().mockResolvedValue([
      { strGameID: "10", hHandle: 7, nCreated: 1, nWidth: 1280, nHeight: 800, strUrl: "https://steamloopback.host/shot.jpg" },
    ]),
    screenshotPath: vi.fn().mockResolvedValue("/home/deck/.local/share/Steam/userdata/1/760/remote/10/screenshots/shot.jpg"),
    measureScreenshotPaths: vi.fn().mockResolvedValue({ "/home/deck/.local/share/Steam/userdata/1/760/remote/10/screenshots/shot.jpg": 123 }),
    listBackgroundRecordings: vi.fn().mockResolvedValue([
      { game_id: "20", most_recent_start_time: 2, video_duration_seconds: 60, file_size: "456", is_active: false },
    ]),
    listClips: vi.fn().mockResolvedValue([
      { clip_id: "clip-1", game_id: "30", duration_ms: "90000", date_recorded: 3, file_size: "789", name: "Victoria", thumbnail_url: "https://steamloopback.host/clip.jpg", temporary: false },
    ]),
    deleteScreenshots: vi.fn().mockResolvedValue({ bSuccess: true, rgFailedRequestIndices: [] }),
    deleteBackgroundRecordings: vi.fn().mockResolvedValue(true),
    deleteClip: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

describe("Steam media inventory", () => {
  it("publishes names and thumbnails before screenshot sizes finish loading", async () => {
    const path = deferred<string | null>();
    const sizes = deferred<Record<string, number | null>>();
    const api = gateway({
      screenshotPath: vi.fn().mockReturnValue(path.promise),
      measureScreenshotPaths: vi.fn().mockReturnValue(sizes.promise),
    });
    const updates: Array<Array<number | null>> = [];
    const running = scanMedia(api, (items) => updates.push(items.map((item) => item.bytes)));

    await vi.waitFor(() => expect(updates).toEqual([[null, 456, 789]]));
    expect(api.measureScreenshotPaths).not.toHaveBeenCalled();
    path.resolve("/home/deck/.local/share/Steam/userdata/1/760/remote/10/screenshots/shot.jpg");
    await vi.waitFor(() => expect(api.measureScreenshotPaths).toHaveBeenCalledOnce());
    sizes.resolve({ "/home/deck/.local/share/Steam/userdata/1/760/remote/10/screenshots/shot.jpg": 123 });
    const items = await running;

    expect(items.map((item) => item.bytes)).toEqual([123, 456, 789]);
    expect(items[0]).toMatchObject({ kind: "screenshot", thumbnailUrl: "https://steamloopback.host/shot.jpg", width: 1280, height: 800 });
    expect(items[2]).toMatchObject({ kind: "clip", title: "Victoria", durationSeconds: 90 });
  });

  it("roots Steam's relative capture URLs at steamloopback", async () => {
    const api = gateway({
      listScreenshots: vi.fn().mockResolvedValue([
        { strGameID: "10", hHandle: 7, nCreated: 1, nWidth: 1280, nHeight: 800, strUrl: "screenshots/10/screenshots/shot.jpg" },
      ]),
      listClips: vi.fn().mockResolvedValue([
        { clip_id: "clip-1", game_id: "30", duration_ms: "90000", date_recorded: 3, file_size: "789", name: "Victoria", thumbnail_url: "/clips/thumb.jpg", temporary: false },
      ]),
    });

    const items = await scanMedia(api, () => undefined);

    expect(items.find((item) => item.kind === "screenshot")?.thumbnailUrl).toBe("https://steamloopback.host/screenshots/10/screenshots/shot.jpg");
    expect(items.find((item) => item.kind === "clip")?.thumbnailUrl).toBe("https://steamloopback.host/clips/thumb.jpg");
  });

  it("marks old disposable data as recommended without selecting it", async () => {
    const items = await scanMedia(gateway(), () => undefined, 365 * 24 * 60 * 60);
    expect(items[0].recommendation).toBe("old_capture");
    expect(items[1].recommendation).toBe("old_recording");
    expect(items[2].recommendation).toBeNull();
    expect(items.every((item) => !("selected" in item))).toBe(true);
  });

  it("stops requesting screenshot paths between bounded batches after leaving Limpieza", async () => {
    let active = true;
    const screenshots = Array.from({ length: 120 }, (_, index) => ({
      strGameID: "10", hHandle: index, nCreated: 1, nWidth: 1280, nHeight: 800, strUrl: `${index}.jpg`,
    }));
    const api = gateway({
      listScreenshots: vi.fn().mockResolvedValue(screenshots),
      listBackgroundRecordings: vi.fn().mockResolvedValue([]),
      listClips: vi.fn().mockResolvedValue([]),
      screenshotPath: vi.fn().mockImplementation(async (_gameId, handle) => {
        if (handle === 49) active = false;
        return `/steam/${handle}.jpg`;
      }),
    });

    await scanMedia(api, () => undefined, undefined, () => active);

    expect(api.screenshotPath).toHaveBeenCalledTimes(50);
    expect(api.measureScreenshotPaths).not.toHaveBeenCalled();
  });

  it("stops measuring screenshot paths between backend-safe batches", async () => {
    let active = true;
    const screenshots = Array.from({ length: 501 }, (_, index) => ({
      strGameID: "10", hHandle: index, nCreated: 1, nWidth: 1280, nHeight: 800, strUrl: `${index}.jpg`,
    }));
    const api = gateway({
      listScreenshots: vi.fn().mockResolvedValue(screenshots),
      listBackgroundRecordings: vi.fn().mockResolvedValue([]),
      listClips: vi.fn().mockResolvedValue([]),
      screenshotPath: vi.fn().mockImplementation(async (_gameId, handle) => `/steam/${handle}.jpg`),
      measureScreenshotPaths: vi.fn().mockImplementation(async (paths: string[]) => {
        active = false;
        return Object.fromEntries(paths.map((path) => [path, 20]));
      }),
    });

    await scanMedia(api, () => undefined, undefined, () => active);

    expect(api.measureScreenshotPaths).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.measureScreenshotPaths).mock.calls[0][0]).toHaveLength(500);
  });

  it("keeps available media and reports incomplete coverage when one Steam API fails", async () => {
    const issues: string[][] = [];
    const api = gateway({ listScreenshots: vi.fn().mockRejectedValue(new Error("unavailable")) });

    const items = await scanMedia(api, () => undefined, undefined, undefined, (sources) => issues.push(sources));

    expect(items.map((item) => item.kind)).toEqual(["recording", "clip"]);
    expect(issues).toEqual([["screenshots"]]);
  });

  it("keeps screenshot rows when their sizes cannot be measured", async () => {
    const issues: string[][] = [];
    const api = gateway({ measureScreenshotPaths: vi.fn().mockRejectedValue(new Error("unavailable")) });

    const items = await scanMedia(api, () => undefined, undefined, undefined, (sources) => issues.push(sources));

    expect(items).toHaveLength(3);
    expect(items.find((item) => item.kind === "screenshot")?.bytes).toBeNull();
    expect(issues).toEqual([[], ["measurement"]]);
  });

  it("deletes through Steam and reports failed screenshot groups honestly", async () => {
    const api = gateway({ deleteScreenshots: vi.fn().mockResolvedValue({ bSuccess: false, rgFailedRequestIndices: [0] }) });
    const items = await scanMedia(api, () => undefined);
    const result = await cleanMedia(api, items);

    expect(api.deleteScreenshots).toHaveBeenCalledWith([{ gameID: "10", rgHandles: [7] }]);
    expect(api.deleteBackgroundRecordings).toHaveBeenCalledWith(["20"]);
    expect(api.deleteClip).toHaveBeenCalledWith("clip-1");
    expect(result.items.map((item) => item.status)).toEqual(["error", "deleted", "deleted"]);
    expect(result.bytesRemoved).toBe(456 + 789);
  });

  it("keeps every screenshot when Steam returns an ambiguous global failure", async () => {
    const api = gateway({ deleteScreenshots: vi.fn().mockResolvedValue({ bSuccess: false, rgFailedRequestIndices: [] }) });
    const items = await scanMedia(api, () => undefined);

    const result = await cleanMedia(api, items.filter((item) => item.kind === "screenshot"));

    expect(result.items[0].status).toBe("error");
    expect(result.bytesRemoved).toBe(0);
  });

  it("keeps every screenshot when Steam returns a failed index outside the request", async () => {
    const api = gateway({ deleteScreenshots: vi.fn().mockResolvedValue({ bSuccess: true, rgFailedRequestIndices: [99] }) });
    const items = await scanMedia(api, () => undefined);

    const result = await cleanMedia(api, items.filter((item) => item.kind === "screenshot"));

    expect(result.items[0].status).toBe("error");
    expect(result.bytesRemoved).toBe(0);
  });

  it("keeps invalid media sizes as unknown", async () => {
    const api = gateway({
      listBackgroundRecordings: vi.fn().mockResolvedValue([{ game_id: "20", most_recent_start_time: 2, video_duration_seconds: Number.NaN, file_size: "invalid", is_active: false }]),
      listClips: vi.fn().mockResolvedValue([{ clip_id: "clip-1", game_id: "30", duration_ms: "", date_recorded: 3, file_size: "", name: "Victoria", thumbnail_url: "", temporary: false }]),
    });

    const items = await scanMedia(api, () => undefined);

    expect(items.find((item) => item.kind === "recording")).toMatchObject({ bytes: null, durationSeconds: null });
    expect(items.find((item) => item.kind === "clip")).toMatchObject({ bytes: null, durationSeconds: null });
  });

  it("rechecks background recording activity before deleting", async () => {
    const api = gateway();
    const items = await scanMedia(api, () => undefined);
    vi.mocked(api.listBackgroundRecordings).mockResolvedValueOnce([
      { game_id: "20", most_recent_start_time: 2, video_duration_seconds: 60, file_size: "456", is_active: true },
    ]);

    const result = await cleanMedia(api, items.filter((item) => item.kind === "recording"));

    expect(api.deleteBackgroundRecordings).not.toHaveBeenCalled();
    expect(result.items[0].status).toBe("error");
  });
});
