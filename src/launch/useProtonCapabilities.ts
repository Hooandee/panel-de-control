import { useEffect, useState } from "react";
import { getProtonCaps } from "../api";

export type ProtonCapabilityStatus = "loading" | "missing" | "error" | "ready";
export interface ProtonCapabilityState {
  status: ProtonCapabilityStatus;
  envs: string[];
}

export function useProtonCapabilities(compatName: string, loading: boolean): ProtonCapabilityState {
  const [snapshot, setSnapshot] = useState<ProtonCapabilityState & { name: string } | null>(null);
  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    setSnapshot(null);
    getProtonCaps(compatName)
      .then((caps) => {
        if (!cancelled) setSnapshot({ name: compatName, status: caps.found ? "ready" : "missing", envs: caps.found ? caps.envs : [] });
      }, () => {
        if (!cancelled) setSnapshot({ name: compatName, status: "error", envs: [] });
      });
    return () => { cancelled = true; };
  }, [compatName, loading]);
  // A new tool must never inherit capabilities from the previous render.
  return !loading && snapshot?.name === compatName ? snapshot : { status: "loading", envs: [] };
}
