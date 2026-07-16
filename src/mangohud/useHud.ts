import { useEffect, useRef, useState } from "react";
import { HudModel, HudState, getHudState, reloadHud, resetHud, setHudConfig, setHudEnabled } from "../api";

const POLL_MS = 4000;
const DEBOUNCE_MS = 250; // coalesce rapid slider/color drags into one write

export type ReloadStatus = "idle" | "busy" | "ok";

export interface HudController {
  state: HudState | null;
  /** Update the whole model (optimistic + debounced persist/apply). */
  setModel: (model: HudModel) => void;
  /** Flip "Mostrar HUD" (writes/clears presets.conf immediately). */
  setEnabled: (enabled: boolean) => void;
  /** Re-push the saved HUD to the live overlay so mangoapp reloads it now. */
  reload: () => void;
  /** Visible feedback for the reload button (busy → ok → idle). */
  reloadStatus: ReloadStatus;
  reset: () => void;
}

export function useHud(): HudController {
  const [state, setState] = useState<HudState | null>(null);
  const [reloadStatus, setReloadStatus] = useState<ReloadStatus>("idle");
  const pending = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const okTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getHudState()
        .then((s) => {
          if (alive && !pending.current) setState(s);
        })
        .catch(() => {});
    };
    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
      if (timer.current) clearTimeout(timer.current);
      if (okTimer.current) clearTimeout(okTimer.current);
    };
  }, []);

  const setModel = (model: HudModel) => {
    setState((prev) => (prev ? { ...prev, model } : prev)); // optimistic
    pending.current = true;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setHudConfig(model)
        .then(setState)
        .catch(() => {})
        .finally(() => {
          pending.current = false;
        });
    }, DEBOUNCE_MS);
  };

  const setEnabled = (enabled: boolean) => {
    setState((prev) => (prev ? { ...prev, model: { ...prev.model, enabled } } : prev));
    pending.current = true;
    setHudEnabled(enabled)
      .then(setState)
      .catch(() => {})
      .finally(() => {
        pending.current = false;
      });
  };

  const reload = () => {
    pending.current = true;
    setReloadStatus("busy");
    if (okTimer.current) clearTimeout(okTimer.current);
    reloadHud()
      .then(setState)
      .catch(() => {})
      .finally(() => {
        pending.current = false;
        setReloadStatus("ok");
        okTimer.current = setTimeout(() => setReloadStatus("idle"), 1800);
      });
  };

  const reset = () => {
    pending.current = true;
    resetHud()
      .then(setState)
      .catch(() => {})
      .finally(() => {
        pending.current = false;
      });
  };

  return { state, setModel, setEnabled, reload, reloadStatus, reset };
}
