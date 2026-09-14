import { useCallback, useEffect, useRef, useState } from "react";
import { recordSteamMediaEvent, type SteamMediaEvent, type SteamMediaSource } from "../api";
import { cleanMedia, scanMedia, type MediaCleanResult, type MediaItem, type MediaSource } from "./media";
import { createSteamMediaGateway } from "./steamMediaGateway";

function record(event: SteamMediaEvent, count = 0, errors = 0, source: SteamMediaSource = "none") {
  void recordSteamMediaEvent(event, count, errors, source).catch(() => undefined);
}

export function useMediaCleaner() {
  const gateway = useRef(createSteamMediaGateway());
  const mounted = useRef(false);
  const epoch = useRef(0);
  const inflight = useRef<"scan" | "clean" | null>(null);
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cleaning, setCleaning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MediaCleanResult | null>(null);

  const scan = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = "scan";
    const revision = ++epoch.current;
    let issues: MediaSource[] = [];
    setLoading(true);
    setError(null);
    record("scan_started");
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
        record("scan_cancelled");
        return;
      }
      for (const source of issues) record("scan_failed", next.length, 1, source);
      if (mounted.current && revision === epoch.current) {
        setItems(next);
        setError(issues.length ? "media_incomplete" : null);
        record("scan_completed", next.length, issues.length);
      }
    } catch {
      for (const source of issues.length ? issues : ["none" as const]) record("scan_failed", 0, 1, source);
      if (mounted.current && revision === epoch.current) {
        setItems([]);
        setError("media_unavailable");
      }
    } finally {
      if (inflight.current === "scan") inflight.current = null;
      if (mounted.current && revision === epoch.current) setLoading(false);
    }
  }, []);

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
    const revision = ++epoch.current;
    inflight.current = "clean";
    setCleaning(true);
    setError(null);
    setResult(null);
    record("cleanup_started", selected.length);
    try {
      const outcome = await cleanMedia(gateway.current, selected);
      const failed = new Set(outcome.items.filter((item) => item.status === "error").map((item) => item.id));
      for (const [source, kind] of [["screenshots", "screenshot"], ["recordings", "recording"], ["clips", "clip"]] as const) {
        const sourceItems = selected.filter((item) => item.kind === kind);
        const errors = sourceItems.filter((item) => failed.has(item.id)).length;
        if (errors) record("cleanup_failed", sourceItems.length, errors, source);
      }
      record("cleanup_completed", outcome.items.length, failed.size);
      if (!mounted.current || revision !== epoch.current) return;
      const deleted = new Set(outcome.items.filter((item) => item.status === "deleted").map((item) => item.id));
      setItems((current) => current.filter((item) => !deleted.has(item.id)));
      setResult(outcome);
    } catch {
      record("cleanup_failed", selected.length, selected.length);
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
