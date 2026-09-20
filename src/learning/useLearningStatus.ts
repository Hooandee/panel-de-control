import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { getLearningStatus, LearningStatus } from "../api";
import {
  getLearningStatusVersion,
  subscribeLearningStatus,
} from "./statusInvalidation";

export function useLearningStatus(appidKey: string | null) {
  const [status, setStatus] = useState<LearningStatus | null>(null);
  const requestId = useRef(0);
  const invalidation = useSyncExternalStore(
    subscribeLearningStatus,
    getLearningStatusVersion,
    getLearningStatusVersion,
  );

  const refresh = useCallback(() => {
    const currentRequest = ++requestId.current;
    getLearningStatus()
      .then((next) => {
        if (requestId.current === currentRequest) setStatus(next);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      requestId.current += 1;
    };
  }, [appidKey, invalidation, refresh]);

  return { status, refresh };
}
