import { useCallback, useEffect, useState } from "react";
import { getLearningStatus, LearningStatus } from "../api";

/**
 * Fetches the learning capability + opt-in snapshot for the banner. Device
 * capabilities (tdp/fan support) are static; `telemetry_enabled` can change (the
 * Ajustes toggle). We refetch when `appidKey` changes — a game change is exactly
 * when the banner's "learning of X" needs a fresh read — and expose `refresh`
 * so the caller can re-pull after toggling telemetry. Returns null until the
 * first RPC lands (banner renders nothing until then — never a fake state).
 */
export function useLearningStatus(appidKey: string | null) {
  const [status, setStatus] = useState<LearningStatus | null>(null);

  const refresh = useCallback(() => {
    getLearningStatus().then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [appidKey, refresh]);

  return { status, refresh };
}
