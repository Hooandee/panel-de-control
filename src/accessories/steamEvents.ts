import { accessoryEvent, accessoryResume, accessorySuspend, getAccessoriesState } from "../api";
import { refreshGameInfo } from "./gameInfo";

const ICON = 24;
const LOCAL_CLIENT = "0";

interface Achievement {
  strName?: string;
  strImage?: string;
  bAchieved?: boolean;
}

interface SuspendEvents {
  RegisterForPrepareForSystemSuspendProgress(callback: () => void): { unregister(): void };
  RegisterForResumeSuspendedGamesProgress(callback: () => void): { unregister(): void };
}

interface Overview {
  remote_client_id?: string;
  update_appid?: number;
  update_state?: string;
  overall_percent_complete?: number;
  overall_estimated_time_remaining_sec?: number;
  paused?: boolean;
}

function iconPixels(url: string): Promise<string | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = ICON;
        canvas.height = ICON;
        const ctx = canvas.getContext("2d")!;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, 0, 0, ICON, ICON);
        const rgba = ctx.getImageData(0, 0, ICON, ICON).data;
        let rgb = "";
        for (let i = 0; i < rgba.length; i += 4) rgb += String.fromCharCode(rgba[i], rgba[i + 1], rgba[i + 2]);
        resolve(btoa(rgb));
      } catch {
        resolve(null);
      }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function appName(appid: number): string {
  try {
    const store = (window as unknown as { appStore?: { GetAppOverviewByAppID(id: number): { display_name?: string } | null } }).appStore;
    return store?.GetAppOverviewByAppID(appid)?.display_name ?? "";
  } catch {
    return "";
  }
}

/** Forwards achievements, suspend and the local download progress to the panel; only on the Steam Machine. */
export function startAccessorySteamEvents(): () => void {
  const registrations: { unregister(): void }[] = [];
  let alive = true;
  let lastDownload = "";

  void getAccessoriesState().then((state) => {
    if (!alive || !state?.supported) return;
    try {
      registrations.push(SteamClient.GameSessions.RegisterForAchievementNotification((notification: unknown) => {
        const raw = (notification as { achievement?: Achievement }).achievement;
        if (!raw || raw.bAchieved === false || !raw.strName) return;
        refreshGameInfo();
        const send = (icon: string | null) => void accessoryEvent("achievement", { title: raw.strName ?? "", icon }).catch(() => undefined);
        if (raw.strImage) void iconPixels(raw.strImage).then(send);
        else send(null);
      }));
    } catch { /* not available on this client */ }
    try {
      const system = SteamClient.User as unknown as SuspendEvents;
      registrations.push(system.RegisterForPrepareForSystemSuspendProgress(() => {
        void accessorySuspend().catch(() => undefined);
      }));
      registrations.push(system.RegisterForResumeSuspendedGamesProgress(() => {
        void accessoryResume().catch(() => undefined);
      }));
    } catch { /* not available on this client */ }
    try {
      registrations.push(SteamClient.Downloads.RegisterForDownloadOverview((payload: unknown) => {
        const list = (Array.isArray(payload) ? payload : [payload]) as Overview[];
        const local = list.find((item) => String(item?.remote_client_id ?? LOCAL_CLIENT) === LOCAL_CLIENT);
        const active = local && local.update_appid && local.update_state !== "None";
        const data = active ? {
          name: appName(local.update_appid!),
          done: Math.round(local.overall_percent_complete ?? 0),
          total: 100,
          seconds: Math.max(0, local.overall_estimated_time_remaining_sec ?? 0),
          paused: !!local.paused,
        } : null;
        const signature = data ? `${data.name}:${data.done}:${data.paused}:${Math.round(data.seconds / 60)}` : "";
        if (signature === lastDownload) return;
        lastDownload = signature;
        void accessoryEvent("download", data ?? {}).catch(() => undefined);
      }));
    } catch { /* not available on this client */ }
  }).catch(() => undefined);

  return () => {
    alive = false;
    registrations.forEach((registration) => {
      try {
        registration.unregister();
      } catch { /* already gone */ }
    });
  };
}
