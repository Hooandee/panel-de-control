export type MediaKind = "screenshot" | "recording" | "clip";
export type MediaRecommendation = "old_capture" | "old_recording" | "temporary_clip";
export type MediaSource = "screenshots" | "recordings" | "clips" | "measurement";
export type MediaFailureReason = "steam_rejected" | "invalid_response" | "item_changed" | "active_recording" | "steam_api_error" | "invalid_item";

export class MediaGatewayError extends Error {
  constructor(readonly reason: "invalid_response" | "steam_api_error") {
    super(reason);
  }
}

export interface SteamScreenshot {
  strGameID: string;
  hHandle: number;
  nCreated: number;
  nWidth: number;
  nHeight: number;
  strUrl: string;
}

export interface SteamBackgroundRecording {
  game_id: string;
  most_recent_start_time: number;
  video_duration_seconds: number;
  file_size: string;
  is_active: boolean;
}

export interface SteamClip {
  clip_id: string;
  game_id: string;
  duration_ms: string;
  date_recorded: number;
  file_size: string;
  name: string;
  thumbnail_url: string;
  temporary: boolean;
}

export interface MediaItem {
  id: string;
  kind: MediaKind;
  gameId: string;
  handle: number | null;
  clipId: string | null;
  title: string | null;
  thumbnailUrl: string | null;
  createdAt: number;
  durationSeconds: number | null;
  width: number | null;
  height: number | null;
  bytes: number | null;
  path: string | null;
  active: boolean;
  recommendation: MediaRecommendation | null;
}

export interface MediaGateway {
  listScreenshots(isActive?: () => boolean): Promise<SteamScreenshot[]>;
  screenshotPath(gameId: string, handle: number): Promise<string | null>;
  measureScreenshotPaths(paths: string[]): Promise<Record<string, number | null>>;
  listBackgroundRecordings(): Promise<SteamBackgroundRecording[]>;
  listClips(): Promise<SteamClip[]>;
  deleteScreenshots(requests: Array<{ gameID: string; rgHandles: number[] }>): Promise<{ bSuccess: unknown; rgFailedRequestIndices: unknown }>;
  deleteBackgroundRecordings(gameIds: string[]): Promise<boolean>;
  deleteClip(clipId: string): Promise<boolean>;
}

export interface MediaCleanResultItem { id: string; status: "deleted" | "error"; reason: MediaFailureReason | null; bytesRemoved: number; }
export interface MediaCleanResult { operationId: string; items: MediaCleanResultItem[]; bytesRemoved: number; }

const DAY = 24 * 60 * 60;
const SCREENSHOT_PATH_BATCH = 50;

export function mediaOperationId(): string {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return hex.match(/.{4}/g)!.join("-");
}

function numberValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function millisecondsToSeconds(value: unknown): number | null {
  const parsed = nullableNumber(value);
  return parsed === null ? null : parsed / 1_000;
}

function mediaImageUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  if (/^(?:https?:\/\/|data:image\/|blob:)/i.test(value)) return value;
  if (value.includes("://")) return null;
  return `https://steamloopback.host/${value.replace(/^\/+/, "")}`;
}

function recommendation(kind: MediaKind, createdAt: number, active: boolean, temporary: boolean, now: number): MediaRecommendation | null {
  if (kind === "clip" && temporary) return "temporary_clip";
  if (active || !createdAt) return null;
  const age = now - createdAt;
  if (kind === "screenshot" && age >= 180 * DAY) return "old_capture";
  if (kind === "recording" && age >= 30 * DAY) return "old_recording";
  return null;
}

export async function scanMedia(
  gateway: MediaGateway,
  onProgress: (items: MediaItem[]) => void,
  now = Math.floor(Date.now() / 1000),
  isActive: () => boolean = () => true,
  onIssues: (sources: MediaSource[]) => void = () => undefined,
): Promise<MediaItem[]> {
  const inventories = await Promise.allSettled([
    gateway.listScreenshots(isActive),
    gateway.listBackgroundRecordings(),
    gateway.listClips(),
  ]);
  if (!isActive()) return [];
  const sources: MediaSource[] = ["screenshots", "recordings", "clips"];
  const issues = inventories.flatMap((result, index) => result.status === "rejected" ? [sources[index]] : []);
  onIssues(issues);
  if (issues.length === inventories.length) throw new Error("media_unavailable");
  const screenshots = inventories[0].status === "fulfilled" ? inventories[0].value : [];
  const recordings = inventories[1].status === "fulfilled" ? inventories[1].value : [];
  const clips = inventories[2].status === "fulfilled" ? inventories[2].value : [];
  const screenshotItems: MediaItem[] = screenshots.map((item) => ({
      id: `screenshot:${item.strGameID}:${item.hHandle}`,
      kind: "screenshot",
      gameId: item.strGameID,
      handle: item.hHandle,
      clipId: null,
      title: null,
      thumbnailUrl: mediaImageUrl(item.strUrl),
      createdAt: numberValue(item.nCreated),
      durationSeconds: null,
      width: numberValue(item.nWidth) || null,
      height: numberValue(item.nHeight) || null,
      bytes: null,
      path: null,
      active: false,
      recommendation: recommendation("screenshot", numberValue(item.nCreated), false, false, now),
    }));
  const recordingItems: MediaItem[] = recordings.map((item) => ({
    id: `recording:${item.game_id}`,
    kind: "recording",
    gameId: item.game_id,
    handle: null,
    clipId: null,
    title: null,
    thumbnailUrl: null,
    createdAt: numberValue(item.most_recent_start_time),
    durationSeconds: nullableNumber(item.video_duration_seconds),
    width: null,
    height: null,
    bytes: nullableNumber(item.file_size),
    path: null,
    active: item.is_active === true,
    recommendation: recommendation("recording", numberValue(item.most_recent_start_time), item.is_active === true, false, now),
  }));
  const clipItems: MediaItem[] = clips.map((item) => ({
    id: `clip:${item.clip_id}`,
    kind: "clip",
    gameId: item.game_id,
    handle: null,
    clipId: item.clip_id,
    title: item.name || null,
    thumbnailUrl: mediaImageUrl(item.thumbnail_url),
    createdAt: numberValue(item.date_recorded),
    durationSeconds: millisecondsToSeconds(item.duration_ms),
    width: null,
    height: null,
    bytes: nullableNumber(item.file_size),
    path: null,
    active: false,
    recommendation: recommendation("clip", numberValue(item.date_recorded), false, item.temporary === true, now),
  }));
  const initial = [...screenshotItems, ...recordingItems, ...clipItems];
  if (!isActive()) return [];
  onProgress(initial);
  const screenshotPaths: Array<string | null> = [];
  for (let first = 0; first < screenshots.length && isActive(); first += SCREENSHOT_PATH_BATCH) {
    const batch = screenshots.slice(first, first + SCREENSHOT_PATH_BATCH);
    screenshotPaths.push(...await Promise.all(batch.map((item) =>
      gateway.screenshotPath(item.strGameID, item.hHandle).catch(() => null),
    )));
  }
  if (!isActive()) return initial;
  const withPaths = initial.map((item, index) => index < screenshotPaths.length ? { ...item, path: screenshotPaths[index] } : item);
  const paths = screenshotPaths.flatMap((path) => path ? [path] : []);
  if (!paths.length) return withPaths;
  const sizes: Record<string, number | null> = {};
  try {
    for (let first = 0; first < paths.length && isActive(); first += 500) {
      Object.assign(sizes, await gateway.measureScreenshotPaths(paths.slice(first, first + 500)));
    }
  } catch {
    onIssues([...issues, "measurement"]);
    return withPaths;
  }
  if (!isActive()) return withPaths;
  const completed = withPaths.map((item) => item.path ? { ...item, bytes: sizes[item.path] ?? null } : item);
  onProgress(completed);
  return completed;
}

export async function cleanMedia(gateway: MediaGateway, selected: MediaItem[], operationId = mediaOperationId()): Promise<MediaCleanResult> {
  const outcomes = new Map<string, { status: "deleted" | "error"; reason: MediaFailureReason | null }>();
  const deleted = (item: MediaItem) => outcomes.set(item.id, { status: "deleted", reason: null });
  const failed = (item: MediaItem, reason: MediaFailureReason) => outcomes.set(item.id, { status: "error", reason });
  const screenshotGroups = new Map<string, MediaItem[]>();
  for (const item of selected) {
    if (item.kind === "screenshot") {
      const group = screenshotGroups.get(item.gameId) ?? [];
      group.push(item);
      screenshotGroups.set(item.gameId, group);
    }
  }
  const requests = [...screenshotGroups].map(([gameID, items]) => ({
    gameID,
    rgHandles: items.flatMap((item) => item.handle === null ? [] : [item.handle]),
  }));
  if (requests.length) {
    try {
      const response = await gateway.deleteScreenshots(requests);
      const rawFailureIndices = response?.rgFailedRequestIndices;
      const validFailureIndices = Array.isArray(rawFailureIndices)
        && rawFailureIndices.every((index: unknown) => Number.isSafeInteger(index) && Number(index) >= 0 && Number(index) < requests.length)
        ? rawFailureIndices as number[]
        : null;
      const validResponse = typeof response?.bSuccess === "boolean" && validFailureIndices !== null;
      const failedIndices = new Set(response.bSuccess === true && validFailureIndices !== null
        ? validFailureIndices
        : requests.map((_, index) => index));
      const reason: MediaFailureReason = validResponse ? "steam_rejected" : "invalid_response";
      [...screenshotGroups.values()].forEach((items, index) => {
        for (const item of items) failedIndices.has(index) ? failed(item, reason) : deleted(item);
      });
    } catch (error) {
      const reason = error instanceof MediaGatewayError ? error.reason : "steam_api_error";
      for (const items of screenshotGroups.values()) for (const item of items) failed(item, reason);
    }
  }
  const recordings = selected.filter((item) => item.kind === "recording");
  if (recordings.length) {
    let current: SteamBackgroundRecording[] | null = null;
    try { current = await gateway.listBackgroundRecordings(); } catch {
      for (const item of recordings) failed(item, "steam_api_error");
    }
    const inactive = recordings.filter((item) => {
      const match = current?.find((value) => value.game_id === item.gameId);
      if (!match) {
        if (current) failed(item, "item_changed");
        return false;
      }
      if (match.is_active) {
        failed(item, "active_recording");
        return false;
      }
      return true;
    });
    if (inactive.length) {
      try {
        const success = await gateway.deleteBackgroundRecordings(inactive.map((item) => item.gameId));
        for (const item of inactive) success ? deleted(item) : failed(item, "steam_rejected");
      } catch (error) {
        const reason = error instanceof MediaGatewayError ? error.reason : "steam_api_error";
        for (const item of inactive) failed(item, reason);
      }
    }
  }
  const clips = selected.filter((item) => item.kind === "clip" && item.clipId);
  for (let first = 0; first < clips.length; first += 25) {
    await Promise.all(clips.slice(first, first + 25).map(async (item) => {
      try {
        const success = await gateway.deleteClip(item.clipId!);
        success ? deleted(item) : failed(item, "steam_rejected");
      } catch (error) {
        failed(item, error instanceof MediaGatewayError ? error.reason : "steam_api_error");
      }
    }));
  }
  for (const item of selected) if (!outcomes.has(item.id)) failed(item, "invalid_item");
  const items = selected.map((item): MediaCleanResultItem => {
    const outcome = outcomes.get(item.id)!;
    return { id: item.id, ...outcome, bytesRemoved: outcome.status === "deleted" ? item.bytes ?? 0 : 0 };
  });
  return {
    operationId,
    items,
    bytesRemoved: items.reduce((sum, item) => sum + item.bytesRemoved, 0),
  };
}
