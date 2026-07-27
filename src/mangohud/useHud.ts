import { useEffect, useRef, useState } from "react";

import { HudModel, HudState, getHudState, reloadHud, resetHud, setHudConfig } from "../api";
import { useMountedRef } from "../hooks/useMountedRef";

const POLL_MS = 4000;
const DEBOUNCE_MS = 250;
const FEEDBACK_MS = 1800;

export type ReloadStatus = "idle" | "busy" | "ok" | "pending" | "error";
export type SaveStatus = "idle" | "saving" | "saved" | "error";

export interface HudController {
  state: HudState | null;
  setModel: (model: HudModel) => void;
  setEnabled: (enabled: boolean) => void;
  reload: () => void;
  reloadStatus: ReloadStatus;
  saveStatus: SaveStatus;
  reset: () => void;
}

export function useHud(): HudController {
  const [state, setState] = useState<HudState | null>(null);
  const [reloadStatus, setReloadStatus] = useState<ReloadStatus>("idle");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const mounted = useMountedRef();
  const stateRef = useRef<HudState | null>(null);
  const modelRef = useRef<HudModel | null>(null);
  const dirtyRef = useRef(false);
  const pendingRef = useRef(0);
  const revisionRef = useRef(0);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const accept = (remote: HudState) => {
    stateRef.current = remote;
    modelRef.current = remote.model;
    setState(remote);
  };

  const clearDebounce = () => {
    if (!debounceTimer.current) return;
    clearTimeout(debounceTimer.current);
    debounceTimer.current = null;
  };

  const scheduleFeedbackReset = () => {
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => {
      if (!mounted.current) return;
      setReloadStatus("idle");
      setSaveStatus("idle");
    }, FEEDBACK_MS);
  };

  const persist = (model: HudModel, revision: number) => {
    pendingRef.current += 1;
    if (mounted.current) setSaveStatus("saving");
    void setHudConfig(model)
      .then((remote) => {
        if (!mounted.current || revision !== revisionRef.current) return;
        accept(remote);
        setSaveStatus(remote.applyStatus === "failed" ? "error" : "saved");
        if (remote.applyStatus !== "failed") scheduleFeedbackReset();
      })
      .catch(() => {
        if (!mounted.current || revision !== revisionRef.current) return;
        setSaveStatus("error");
      })
      .finally(() => {
        pendingRef.current = Math.max(0, pendingRef.current - 1);
      });
  };

  useEffect(() => {
    const tick = () => {
      if (dirtyRef.current || pendingRef.current > 0) return;
      const revision = revisionRef.current;
      getHudState()
        .then((remote) => {
          if (
            mounted.current
            && revision === revisionRef.current
            && !dirtyRef.current
            && pendingRef.current === 0
          ) {
            accept(remote);
          }
        })
        .catch(() => {});
    };

    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      clearInterval(poll);
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
      if (debounceTimer.current && modelRef.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
        dirtyRef.current = false;
        revisionRef.current += 1;
        void setHudConfig(modelRef.current);
      }
    };
  }, []);

  const setModel = (model: HudModel) => {
    const current = stateRef.current;
    if (!current) return;
    const optimistic = { ...current, model };
    stateRef.current = optimistic;
    modelRef.current = model;
    dirtyRef.current = true;
    revisionRef.current += 1;
    setState(optimistic);
    setSaveStatus("idle");
    clearDebounce();
    debounceTimer.current = setTimeout(() => {
      debounceTimer.current = null;
      dirtyRef.current = false;
      persist(modelRef.current ?? model, revisionRef.current);
    }, DEBOUNCE_MS);
  };

  const setEnabled = (enabled: boolean) => {
    const current = stateRef.current;
    const latest = modelRef.current;
    if (!current || !latest) return;
    clearDebounce();
    dirtyRef.current = false;
    const model = { ...latest, enabled };
    const optimistic = { ...current, model };
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    stateRef.current = optimistic;
    modelRef.current = model;
    setState(optimistic);
    persist(model, revision);
  };

  const reload = () => {
    const latest = modelRef.current;
    if (!latest) return;
    const hadUnsavedModel = dirtyRef.current;
    clearDebounce();
    dirtyRef.current = false;
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    pendingRef.current += 1;
    setReloadStatus("busy");
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);

    const flush = hadUnsavedModel ? setHudConfig(latest) : Promise.resolve(null);
    void flush
      .then(() => reloadHud())
      .then((remote) => {
        if (!mounted.current || revision !== revisionRef.current) return;
        accept(remote);
        if (remote.applyStatus === "failed" || remote.applyStatus === "unavailable") {
          setReloadStatus("error");
        } else if (remote.applyStatus === "pending") {
          setReloadStatus("pending");
        } else {
          setReloadStatus("ok");
          scheduleFeedbackReset();
        }
      })
      .catch(() => {
        if (!mounted.current || revision !== revisionRef.current) return;
        setReloadStatus("error");
      })
      .finally(() => {
        pendingRef.current = Math.max(0, pendingRef.current - 1);
      });
  };

  const reset = () => {
    clearDebounce();
    dirtyRef.current = false;
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    pendingRef.current += 1;
    setSaveStatus("saving");
    void resetHud()
      .then((remote) => {
        if (!mounted.current || revision !== revisionRef.current) return;
        accept(remote);
        setSaveStatus(remote.applyStatus === "failed" ? "error" : "saved");
        if (remote.applyStatus !== "failed") scheduleFeedbackReset();
      })
      .catch(() => {
        if (!mounted.current || revision !== revisionRef.current) return;
        setSaveStatus("error");
      })
      .finally(() => {
        pendingRef.current = Math.max(0, pendingRef.current - 1);
      });
  };

  return { state, setModel, setEnabled, reload, reloadStatus, saveStatus, reset };
}
