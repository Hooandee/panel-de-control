import { findModuleByExport } from "@decky/ui";
import { measureSteamScreenshotPaths } from "../api";
import type {
  MediaGateway,
  SteamBackgroundRecording,
  SteamClip,
  SteamScreenshot,
} from "./media";

/* eslint-disable @typescript-eslint/no-explicit-any */

interface RecordingService {
  GetClipsHandler?: { name?: string };
  GetAppsWithBackgroundVideo?: (request: object) => Promise<any>;
  GetClips?: (request: object) => Promise<any>;
  ManuallyDeleteRecordingsForApps?: (request: object) => Promise<any>;
  DeleteClip?: (request: object) => Promise<any>;
}

interface ScreenshotService {
  GetAllAppsLocalScreenshotsCount?: () => Promise<number>;
  GetAllAppsLocalScreenshotsRange?: (first: number, last: number) => Promise<SteamScreenshot[]>;
  GetLocalScreenshotPath?: (gameId: string, handle: number) => Promise<string>;
  DeleteLocalScreenshots?: (requests: Array<{ gameID: string; rgHandles: number[] }>) => Promise<{ bSuccess?: boolean; rgFailedRequestIndices?: number[] }>;
}

function recordingService(): RecordingService | null {
  try {
    const module = findModuleByExport(
      (value: any) => value?.GetClipsHandler?.name === "GameRecording.GetClips#1",
    ) as Record<string, unknown> | undefined;
    if (!module) return null;
    return Object.values(module).find(
      (value: any) => value?.GetClipsHandler?.name === "GameRecording.GetClips#1",
    ) as RecordingService | undefined ?? null;
  } catch {
    return null;
  }
}

function screenshots(): ScreenshotService | null {
  try {
    return (window as any).SteamClient?.Screenshots ?? null;
  } catch {
    return null;
  }
}

async function body<T>(operation: Promise<any> | undefined, key: string): Promise<T[]> {
  if (!operation) throw new Error("media_unavailable");
  try {
    const response = await operation;
    if (typeof response?.BSuccess !== "function" || !response.BSuccess()) throw new Error("media_unavailable");
    const object = response?.Body?.().toObject?.();
    if (!object || typeof object !== "object") throw new Error("media_unavailable");
    const value = object[key];
    if (value === undefined) return [];
    if (!Array.isArray(value)) throw new Error("media_unavailable");
    return value as T[];
  } catch {
    throw new Error("media_unavailable");
  }
}

async function success(operation: Promise<any> | undefined): Promise<boolean> {
  if (!operation) return false;
  try {
    const response = await operation;
    return typeof response?.BSuccess === "function" ? response.BSuccess() === true : false;
  } catch {
    return false;
  }
}

export function createSteamMediaGateway(): MediaGateway {
  return {
    async listScreenshots(isActive = () => true) {
      const service = screenshots();
      if (!service?.GetAllAppsLocalScreenshotsCount || !service.GetAllAppsLocalScreenshotsRange) throw new Error("media_unavailable");
      try {
        const total = Number(await service.GetAllAppsLocalScreenshotsCount());
        if (!Number.isSafeInteger(total) || total < 0 || total > 10_000) throw new Error("media_unavailable");
        const result: SteamScreenshot[] = [];
        for (let first = 0; first < total && isActive(); first += 1_000) {
          const last = Math.min(total - 1, first + 999);
          const values = await service.GetAllAppsLocalScreenshotsRange(first, last);
          if (!Array.isArray(values)) throw new Error("media_unavailable");
          result.push(...values);
        }
        return result;
      } catch {
        throw new Error("media_unavailable");
      }
    },
    async screenshotPath(gameId, handle) {
      try {
        const value = await screenshots()?.GetLocalScreenshotPath?.(gameId, handle);
        return typeof value === "string" && value ? value : null;
      } catch {
        return null;
      }
    },
    measureScreenshotPaths: (paths) => measureSteamScreenshotPaths(paths),
    listBackgroundRecordings: () => body<SteamBackgroundRecording>(
      recordingService()?.GetAppsWithBackgroundVideo?.({}),
      "apps",
    ),
    listClips: () => body<SteamClip>(recordingService()?.GetClips?.({}), "clip"),
    async deleteScreenshots(requests) {
      try {
        const response = await screenshots()?.DeleteLocalScreenshots?.(requests);
        return {
          bSuccess: response?.bSuccess === true,
          rgFailedRequestIndices: Array.isArray(response?.rgFailedRequestIndices)
            && response.rgFailedRequestIndices.every((index: unknown) => Number.isSafeInteger(index) && Number(index) >= 0 && Number(index) < requests.length)
            ? response.rgFailedRequestIndices
            : requests.map((_, index) => index),
        };
      } catch {
        return { bSuccess: false, rgFailedRequestIndices: requests.map((_, index) => index) };
      }
    },
    deleteBackgroundRecordings: (gameIds) => success(
      recordingService()?.ManuallyDeleteRecordingsForApps?.({ game_ids: gameIds }),
    ),
    deleteClip: (clipId) => success(recordingService()?.DeleteClip?.({ clip_id: clipId })),
  };
}
