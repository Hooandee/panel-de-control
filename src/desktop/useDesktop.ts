import { useCallback, useEffect, useState } from "react";

import {
  DesktopPowerMode,
  DesktopState,
  getDesktopState,
  retryDesktopMigration,
  setDesktopModeEnabled,
  setDesktopPowerLimits,
  setDesktopPowerMode,
} from "../api";

export function useDesktopState(poll = false) {
  const [state, setState] = useState<DesktopState | null>(null);
  const [error, setError] = useState(false);
  const refresh = useCallback(() => {
    getDesktopState()
      .then((next) => { setState(next); setError(false); })
      .catch(() => setError(true));
  }, []);
  useEffect(() => {
    refresh();
    if (!poll) return;
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [poll, refresh]);
  const setEnabled = useCallback((enabled: boolean) => {
    setDesktopModeEnabled(enabled)
      .then((next) => { setState(next); setError(false); })
      .catch(() => setError(true));
  }, []);
  const applyMode = useCallback((mode: DesktopPowerMode) => {
    setDesktopPowerMode(mode).then(() => refresh()).catch(() => setError(true));
  }, [refresh]);
  const applyLimits = useCallback((cpu: number, gpu: number) => {
    setDesktopPowerLimits(cpu, gpu).then(() => refresh()).catch(() => setError(true));
  }, [refresh]);
  const retryMigration = useCallback(() => {
    retryDesktopMigration()
      .then((next) => { setState(next); setError(false); })
      .catch(() => setError(true));
  }, []);
  return { state, error, refresh, retryMigration, setEnabled, applyMode, applyLimits };
}
