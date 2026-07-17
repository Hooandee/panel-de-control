import { useCallback, useEffect, useRef, useState } from "react";

import { getTdpConflict, getTdpControlEnabled, getTdpState, takeTdpControl } from "../api";
import {
  ConflictResult,
  SDTDP_NAME,
  monitorOnly as computeMonitorOnly,
  sdtdpActive,
  tdpConflict,
} from "./conflict";
import { disablePlugin, disabledPlugins, installedPlugins } from "./deckyPlugins";

export interface TdpConflictHook {
  conflict: boolean;
  rivals: ConflictResult["rivals"];
  monitorOnly: boolean;
  // Turn off SimpleDeckyTDP (Decky) — reversible from Decky.
  disableSdtdp: () => Promise<void>;
  // Hand HHD's TDP module over to us (reversible; restored on release/unload).
  takeHhd: () => Promise<void>;
  // Turn off every active rival in one gesture.
  takeAll: () => Promise<void>;
}

/**
 * Detects rival TDP managers and exposes reversible actions to disable them.
 * Combines HHD (backend RPC) + SimpleDeckyTDP (Decky plugin list) with whether
 * WE control TDP (hardware support + master switch). Polls lightly while mounted.
 */
export function useTdpConflict(): TdpConflictHook {
  const [hhdManaging, setHhdManaging] = useState(false);
  const [sdtdp, setSdtdp] = useState(false);
  const [supported, setSupported] = useState(false);
  const [weControl, setWeControl] = useState(false);
  const alive = useRef(true);

  const refetch = useCallback(async () => {
    // Read the pieces independently so one failing RPC doesn't blank the rest.
    const [conflictRes, enabled, state] = await Promise.all([
      getTdpConflict().catch(() => null),
      getTdpControlEnabled().catch(() => null),
      getTdpState().catch(() => null),
    ]);
    if (!alive.current) return;
    if (conflictRes) setHhdManaging(!!conflictRes.hhd_managing);
    if (enabled !== null) setWeControl(!!enabled);
    if (state) setSupported(!!state.supported);
    setSdtdp(sdtdpActive(installedPlugins(), disabledPlugins()));
  }, []);

  useEffect(() => {
    alive.current = true;
    void refetch();
    const id = setInterval(() => void refetch(), 3000);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [refetch]);

  const { conflict, rivals } = tdpConflict({ sdtdp, hhdManaging, weControl, tdpSupported: supported });

  const disableSdtdp = useCallback(async () => {
    await disablePlugin(SDTDP_NAME);
    await refetch();
  }, [refetch]);

  const takeHhd = useCallback(async () => {
    await takeTdpControl().catch(() => {});
    await refetch();
  }, [refetch]);

  const takeAll = useCallback(async () => {
    if (sdtdp) await disablePlugin(SDTDP_NAME);
    if (hhdManaging) await takeTdpControl().catch(() => {});
    await refetch();
  }, [sdtdp, hhdManaging, refetch]);

  return {
    conflict,
    rivals,
    monitorOnly: computeMonitorOnly(supported, weControl),
    disableSdtdp,
    takeHhd,
    takeAll,
  };
}
