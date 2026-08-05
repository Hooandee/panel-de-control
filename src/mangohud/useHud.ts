import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  HudModel,
  HudState,
  getHudState,
  reloadHud,
  resetHud,
  resolveHudConflict,
  setHudConfig,
} from "../api";
import { useMountedRef } from "../hooks/useMountedRef";

const POLL_MS = 4000;
const DEBOUNCE_MS = 700;
const FEEDBACK_MS = 1800;
export const HUD_RPC_TIMEOUT_MS = 4000;

type HudValues = HudState["values"];

let hudValuesSnapshot: HudValues = {};
const hudValuesSubscribers = new Set<() => void>();

const sameHudValues = (left: HudValues, right: HudValues): boolean => {
  if (left === right) return true;
  const leftKeys = Object.keys(left) as Array<keyof HudValues>;
  const rightKeys = Object.keys(right) as Array<keyof HudValues>;
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key) => left[key] === right[key]);
};

const publishHudValues = (values: HudValues) => {
  if (sameHudValues(hudValuesSnapshot, values)) return;
  hudValuesSnapshot = values;
  hudValuesSubscribers.forEach((notify) => notify());
};

const subscribeHudValues = (notify: () => void) => {
  hudValuesSubscribers.add(notify);
  return () => hudValuesSubscribers.delete(notify);
};

export const useHudValues = (): HudValues => useSyncExternalStore(
  subscribeHudValues,
  () => hudValuesSnapshot,
  () => hudValuesSnapshot,
);

const hudControlSignature = ({ values: _values, ...control }: HudState) =>
  JSON.stringify(control);

export class HudRpcTimeout extends Error {
  constructor() {
    super("HUD RPC timed out");
    this.name = "HudRpcTimeout";
  }
}

export function withHudTimeout<T>(promise: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new HudRpcTimeout());
    }, HUD_RPC_TIMEOUT_MS);
    promise.then(
      (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

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
  resolveConflict: (action: "keep_external" | "use_pdc") => void;
}

const isApplyError = (status: HudState["applyStatus"]) =>
  status === "failed" || status === "conflict" || status === "ambiguous";

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
  const persistingRef = useRef(false);
  const queuedPersistRef = useRef<{ model: HudModel; revision: number } | null>(null);
  const drainWaitersRef = useRef<Array<() => void>>([]);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveFeedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reloadFeedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingRef = useRef(false);
  const commandPendingRef = useRef(false);
  const commandInFlightRef = useRef(false);
  const controlSignatureRef = useRef<string | null>(null);

  const accept = (remote: HudState) => {
    const signature = hudControlSignature(remote);
    stateRef.current = remote;
    modelRef.current = remote.model;
    publishHudValues(remote.values);
    if (signature !== controlSignatureRef.current) {
      controlSignatureRef.current = signature;
      setState(remote);
    }
  };

  const clearDebounce = () => {
    if (!debounceTimer.current) return;
    clearTimeout(debounceTimer.current);
    debounceTimer.current = null;
  };

  const clearSaveFeedback = () => {
    if (!saveFeedbackTimer.current) return;
    clearTimeout(saveFeedbackTimer.current);
    saveFeedbackTimer.current = null;
  };

  const clearReloadFeedback = () => {
    if (!reloadFeedbackTimer.current) return;
    clearTimeout(reloadFeedbackTimer.current);
    reloadFeedbackTimer.current = null;
  };

  const scheduleSaveFeedbackReset = () => {
    clearSaveFeedback();
    saveFeedbackTimer.current = setTimeout(() => {
      if (!mounted.current) return;
      setSaveStatus("idle");
    }, FEEDBACK_MS);
  };

  const scheduleReloadFeedbackReset = () => {
    clearReloadFeedback();
    reloadFeedbackTimer.current = setTimeout(() => {
      if (!mounted.current) return;
      setReloadStatus("idle");
    }, FEEDBACK_MS);
  };

  const waitForPersistDrain = (): Promise<void> => {
    if (!persistingRef.current && !queuedPersistRef.current) return Promise.resolve();
    return new Promise((resolve) => {
      drainWaitersRef.current.push(resolve);
    });
  };

  const resolvePersistDrain = () => {
    if (persistingRef.current || queuedPersistRef.current) return;
    const waiters = drainWaitersRef.current.splice(0);
    waiters.forEach((resolve) => resolve());
  };

  const runCommand = (
    requestFactory: () => Promise<HudState>,
    revision: number,
    onSuccess: (remote: HudState) => void,
    onError: () => void,
  ) => {
    commandPendingRef.current = true;
    pendingRef.current += 1;
    const release = () => {
      pendingRef.current = Math.max(0, pendingRef.current - 1);
      commandPendingRef.current = false;
      commandInFlightRef.current = false;
      const queued = queuedPersistRef.current;
      queuedPersistRef.current = null;
      if (queued) persist(queued.model, queued.revision);
    };
    void waitForPersistDrain()
      .then(() => {
        commandInFlightRef.current = true;
        const request = requestFactory();
        void withHudTimeout(request)
          .then((remote) => {
            if (!mounted.current || revision !== revisionRef.current) return;
            onSuccess(remote);
          })
          .catch(() => {
            if (!mounted.current || revision !== revisionRef.current) return;
            onError();
          });
        void request.catch(() => {}).finally(release);
      })
      .catch(() => {
        if (mounted.current && revision === revisionRef.current) onError();
        release();
      });
  };

  const persist = (model: HudModel, revision: number) => {
    if (persistingRef.current || commandInFlightRef.current) {
      queuedPersistRef.current = { model, revision };
      if (mounted.current) setSaveStatus("saving");
      return;
    }

    persistingRef.current = true;
    pendingRef.current += 1;
    if (mounted.current) {
      clearSaveFeedback();
      setSaveStatus("saving");
    }
    const request = setHudConfig(model);
    void withHudTimeout(request)
      .then((remote) => {
        if (!mounted.current || revision !== revisionRef.current) return;
        accept(remote);
        setSaveStatus(isApplyError(remote.applyStatus) ? "error" : "saved");
        if (!isApplyError(remote.applyStatus)) scheduleSaveFeedbackReset();
      })
      .catch(() => {
        if (!mounted.current) return;
        setSaveStatus("error");
      });
    void request
      .catch(() => {})
      .finally(() => {
        pendingRef.current = Math.max(0, pendingRef.current - 1);
        persistingRef.current = false;
        const queued = queuedPersistRef.current;
        queuedPersistRef.current = null;
        if (queued) {
          persist(queued.model, queued.revision);
        } else {
          resolvePersistDrain();
        }
      });
  };

  useEffect(() => {
    const tick = () => {
      if (dirtyRef.current || pendingRef.current > 0 || pollingRef.current) return;
      const revision = revisionRef.current;
      pollingRef.current = true;
      const request = getHudState();
      void withHudTimeout(request)
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
      void request
        .catch(() => {})
        .finally(() => {
          pollingRef.current = false;
        });
    };

    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      clearInterval(poll);
      clearSaveFeedback();
      clearReloadFeedback();
      if (debounceTimer.current && modelRef.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
        dirtyRef.current = false;
        revisionRef.current += 1;
        persist(modelRef.current, revisionRef.current);
      }
    };
  }, []);

  const setModel = (model: HudModel) => {
    const current = stateRef.current;
    if (!current) return;
    const optimistic = { ...current, model };
    stateRef.current = optimistic;
    modelRef.current = model;
    controlSignatureRef.current = hudControlSignature(optimistic);
    dirtyRef.current = true;
    revisionRef.current += 1;
    setState(optimistic);
    clearSaveFeedback();
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
    controlSignatureRef.current = hudControlSignature(optimistic);
    setState(optimistic);
    persist(model, revision);
  };

  const reload = () => {
    if (commandPendingRef.current || commandInFlightRef.current) return;
    const latest = modelRef.current;
    if (!latest) return;
    const hadUnsavedModel = dirtyRef.current;
    clearDebounce();
    dirtyRef.current = false;
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    if (hadUnsavedModel) persist(latest, revision);
    clearReloadFeedback();
    setReloadStatus("busy");

    runCommand(
      reloadHud,
      revision,
      (remote) => {
        accept(remote);
        if (
          isApplyError(remote.applyStatus)
          || remote.applyStatus === "unavailable"
        ) {
          setReloadStatus("error");
        } else if (
          remote.applyStatus === "pending"
          || remote.applyStatus === "written"
        ) {
          setReloadStatus("pending");
        } else {
          setReloadStatus("ok");
          scheduleReloadFeedbackReset();
        }
      },
      () => setReloadStatus("error"),
    );
  };

  const reset = () => {
    if (commandPendingRef.current || commandInFlightRef.current) return;
    clearDebounce();
    dirtyRef.current = false;
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    queuedPersistRef.current = null;
    clearSaveFeedback();
    setSaveStatus("saving");
    runCommand(
      resetHud,
      revision,
      (remote) => {
        accept(remote);
        setSaveStatus(isApplyError(remote.applyStatus) ? "error" : "saved");
        if (!isApplyError(remote.applyStatus)) scheduleSaveFeedbackReset();
      },
      () => setSaveStatus("error"),
    );
  };

  const resolveConflict = (action: "keep_external" | "use_pdc") => {
    if (commandPendingRef.current || commandInFlightRef.current) return;
    const latest = modelRef.current;
    if (!latest) return;
    const hadUnsavedModel = dirtyRef.current;
    clearDebounce();
    dirtyRef.current = false;
    const revision = revisionRef.current + 1;
    revisionRef.current = revision;
    if (hadUnsavedModel) persist(latest, revision);
    clearSaveFeedback();
    setSaveStatus("saving");

    runCommand(
      () => resolveHudConflict(action),
      revision,
      (remote) => {
        accept(remote);
        setSaveStatus(isApplyError(remote.applyStatus) ? "error" : "saved");
        if (!isApplyError(remote.applyStatus)) scheduleSaveFeedbackReset();
      },
      () => setSaveStatus("error"),
    );
  };

  return {
    state,
    setModel,
    setEnabled,
    reload,
    reloadStatus,
    saveStatus,
    reset,
    resolveConflict,
  };
}
