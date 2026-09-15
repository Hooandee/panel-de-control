import { useCallback, useEffect, useRef, useState } from "react";
import { recordSteamMediaEvent, type SteamMediaEvent, type SteamMediaReason, type SteamMediaSource } from "../api";
import { cleanMedia, mediaOperationId, scanMedia, type MediaCleanResult, type MediaFailureReason, type MediaItem, type MediaSource } from "./media";
import { createSteamMediaGateway } from "./steamMediaGateway";

const sourceFor = (item: MediaItem): SteamMediaSource => item.kind === "screenshot" ? "screenshots" : item.kind === "recording" ? "recordings" : "clips";

export function useMediaCleaner() {
  const gateway = useRef(createSteamMediaGateway());
  const mounted = useRef(false);
  const epoch = useRef(0);
  const inflight = useRef<"scan" | "clean" | null>(null);
  const diagnosticQueue = useRef<Promise<void>>(Promise.resolve());
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cleaning, setCleaning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MediaCleanResult | null>(null);

  const record = useCallback((event: SteamMediaEvent, operationId: string, count = 0, errors = 0, source: SteamMediaSource = "none", reason: SteamMediaReason = "none") => {
    diagnosticQueue.current = diagnosticQueue.current.then(async () => {
      try { await recordSteamMediaEvent(event, operationId, count, errors, source, reason); } catch { /* diagnostics never block cleanup */ }
    });
  }, []);

  const scan = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = "scan";
    const operationId = mediaOperationId();
    const revision = ++epoch.current;
    let issues: MediaSource[] = [];
    setLoading(true);
    setError(null);
    record("scan_started", operationId);
    try {
      const next = await scanMedia(
        gateway.current,
        (progress) => {
          if (mounted.current && revision === epoch.current) setItems(progress);
        },
        Math.floor(Date.now() / 1000),
        () => mounted.current && revision === epoch.current,
        (sources) => { issues = sources; },
      );
      if (!mounted.current || revision !== epoch.current) {
        record("scan_cancelled", operationId, 0, 0, "none", "section_closed");
        return;
      }
      for (const source of issues) record("scan_failed", operationId, next.length, 1, source, source === "measurement" ? "measurement_failed" : "steam_api_error");
      if (mounted.current && revision === epoch.current) {
        setItems(next);
        setError(issues.length ? "media_incomplete" : null);
        record("scan_completed", operationId, next.length, issues.length);
      }
    } catch {
      for (const source of issues) record("scan_failed", operationId, 0, 1, source, "steam_api_error");
      record("scan_failed", operationId, 0, Math.max(issues.length, 1), "none", "steam_api_error");
      if (mounted.current && revision === epoch.current) {
        setItems([]);
        setError("media_unavailable");
      }
    } finally {
      if (inflight.current === "scan") inflight.current = null;
      if (mounted.current && revision === epoch.current) setLoading(false);
    }
  }, [record]);

  useEffect(() => {
    mounted.current = true;
    void scan();
    return () => {
      mounted.current = false;
      epoch.current += 1;
    };
  }, [scan]);

  const clean = async (ids: string[]) => {
    if (inflight.current || !ids.length) return;
    const selected = items.filter((item) => ids.includes(item.id));
    if (!selected.length) return;
    const operationId = mediaOperationId();
    const revision = ++epoch.current;
    inflight.current = "clean";
    setCleaning(true);
    setError(null);
    setResult(null);
    record("cleanup_started", operationId, selected.length);
    try {
      const outcome = await cleanMedia(gateway.current, selected, operationId);
      const failures = outcome.items.filter((item) => item.status === "error");
      const selectedById = new Map(selected.map((item) => [item.id, item]));
      const selectedCounts = new Map<SteamMediaSource, number>();
      for (const item of selected) {
        const source = sourceFor(item);
        selectedCounts.set(source, (selectedCounts.get(source) ?? 0) + 1);
      }
      const failureGroups = new Map<string, { source: SteamMediaSource; reason: MediaFailureReason; errors: number }>();
      for (const failure of failures) {
        const item = selectedById.get(failure.id);
        if (!item) continue;
        const source = sourceFor(item);
        const reason = failure.reason ?? "invalid_item";
        const key = `${source}:${reason}`;
        const group = failureGroups.get(key) ?? { source, reason, errors: 0 };
        group.errors += 1;
        failureGroups.set(key, group);
      }
      for (const group of failureGroups.values()) {
        record("cleanup_failed", operationId, selectedCounts.get(group.source) ?? 0, group.errors, group.source, group.reason);
      }
      record("cleanup_completed", operationId, outcome.items.length, failures.length);
      if (!mounted.current || revision !== epoch.current) return;
      const deleted = new Set(outcome.items.filter((item) => item.status === "deleted").map((item) => item.id));
      setItems((current) => current.filter((item) => !deleted.has(item.id)));
      setResult(outcome);
    } catch {
      record("cleanup_failed", operationId, selected.length, selected.length, "none", "steam_api_error");
      if (mounted.current && revision === epoch.current) {
        setError("media_delete_failed");
      }
    } finally {
      if (inflight.current === "clean") inflight.current = null;
      if (mounted.current && revision === epoch.current) setCleaning(false);
    }
  };

  return {
    items,
    loading,
    cleaning,
    busy: loading || cleaning,
    error,
    result,
    scan,
    clean,
    dismissResult: () => setResult(null),
  };
}

export type MediaCleanerController = ReturnType<typeof useMediaCleaner>;
