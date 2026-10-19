import { useCallback, useEffect, useSyncExternalStore } from "react";
import { toaster } from "@decky/api";
import {
  checkUpdate,
  installUpdate,
  restartLoader,
  type InstallResult,
  type UpdateInfo,
} from "../api";
import type { Lang } from "../i18n";
import { getUpdaterStrings } from "./strings";

// Session-scoped guards: the check runs once per Steam session (the backend also caches),
// and the "update available" toast fires at most once per session. Module-level so they
// survive component remounts and are shared no matter where useUpdate is called.
let sessionChecked = false;
let sessionToasted = false;

export type UpdateStatus = "idle" | "checking" | "installing" | "done" | "error";

let session: { info: UpdateInfo | null; status: UpdateStatus } = { info: null, status: "idle" };
const listeners = new Set<() => void>();
const getSnapshot = () => session;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function publish(update: Partial<typeof session>): void {
  session = { ...session, ...update };
  listeners.forEach((listener) => listener());
}

function checkStatus(status: UpdateStatus): UpdateStatus {
  return session.status === "installing" || session.status === "done" ? session.status : status;
}

export interface UseUpdate {
  info: UpdateInfo | null;
  status: UpdateStatus;
  hasUpdate: boolean;
  check: () => Promise<UpdateInfo | null>;
  install: () => Promise<InstallResult | null>;
  restart: () => void;
}

export function useUpdate(lang: Lang): UseUpdate {
  const { info, status } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const runCheck = useCallback(
    async (force: boolean): Promise<UpdateInfo | null> => {
      publish({ status: checkStatus("checking") });
      try {
        const res = await checkUpdate(force);
        publish({ info: res, status: checkStatus(res.error ? "error" : "idle") });
        if (res.has_update && !sessionToasted) {
          sessionToasted = true;
          toaster.toast({
            title: getUpdaterStrings(lang).availableTitle,
            body: `v${res.latest}`,
          });
        }
        return res;
      } catch {
        publish({ status: checkStatus("error") });
        return null;
      }
    },
    [lang],
  );

  useEffect(() => {
    if (sessionChecked) return;
    sessionChecked = true;
    void runCheck(false);
  }, [runCheck]);

  const install = useCallback(async (): Promise<InstallResult | null> => {
    publish({ status: "installing" });
    try {
      const res = await installUpdate();
      publish({ status: res.ok ? "done" : "error" });
      return res;
    } catch {
      publish({ status: "error" });
      return null;
    }
  }, []);

  return {
    info,
    status,
    hasUpdate: !!info?.has_update,
    check: () => runCheck(true),
    install,
    restart: restartLoader,
  };
}
