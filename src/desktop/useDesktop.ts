import { useCallback, useEffect, useState } from "react";

import {
  DesktopPowerMode,
  DesktopState,
  getDesktopState,
  setDesktopModeEnabled,
  setDesktopPowerLimits,
  setDesktopPowerMode,
} from "../api";

export function useDesktopState(poll = false) {
  const [state, setState] = useState<DesktopState | null>(null);
  const refresh = useCallback(() => {
    getDesktopState().then(setState).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    if (!poll) return;
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [poll, refresh]);
  const setEnabled = useCallback((enabled: boolean) => {
    setDesktopModeEnabled(enabled).then(setState).catch(() => {});
  }, []);
  const applyMode = useCallback((mode: DesktopPowerMode) => {
    setDesktopPowerMode(mode).then(() => refresh()).catch(() => {});
  }, [refresh]);
  const applyLimits = useCallback((cpu: number, gpu: number) => {
    setDesktopPowerLimits(cpu, gpu).then(() => refresh()).catch(() => {});
  }, [refresh]);
  return { state, refresh, setEnabled, applyMode, applyLimits };
}
