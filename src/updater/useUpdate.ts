import { useCallback, useEffect, useState } from "react";
import { toaster } from "@decky/api";
import {
  checkUpdate,
  installUpdate,
  restartLoader,
  type InstallResult,
  type UpdateInfo,
} from "../api";

// Session-scoped guards: the check runs once per Steam session (the backend also caches),
// and the "update available" toast fires at most once per session. Module-level so they
// survive component remounts and are shared no matter where useUpdate is called.
let sessionChecked = false;
let sessionToasted = false;
let sessionInfo: UpdateInfo | null = null;

export type UpdateStatus = "idle" | "checking" | "installing" | "done" | "error";

export interface UseUpdate {
  info: UpdateInfo | null;
  status: UpdateStatus;
  hasUpdate: boolean;
  check: () => Promise<UpdateInfo | null>;
  install: () => Promise<InstallResult | null>;
  restart: () => void;
}

export function useUpdate(lang: "es" | "en"): UseUpdate {
  const [info, setInfo] = useState<UpdateInfo | null>(sessionInfo);
  const [status, setStatus] = useState<UpdateStatus>("idle");

  const runCheck = useCallback(
    async (force: boolean): Promise<UpdateInfo | null> => {
      setStatus("checking");
      try {
        const res = await checkUpdate(force);
        sessionInfo = res;
        setInfo(res);
        setStatus(res.error ? "error" : "idle");
        if (res.has_update && !sessionToasted) {
          sessionToasted = true;
          toaster.toast({
            title: lang === "es" ? "Actualización disponible" : "Update available",
            body: `v${res.latest}`,
          });
        }
        return res;
      } catch {
        setStatus("error");
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
    setStatus("installing");
    try {
      const res = await installUpdate();
      setStatus(res.ok ? "done" : "error");
      return res;
    } catch {
      setStatus("error");
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
