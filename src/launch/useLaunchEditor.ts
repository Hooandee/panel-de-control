import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { bumpLaunchUsage, getLaunchUsage } from "../api";
import { Parsed, parse, serialize } from "./compose";
import { CATALOG, Pill, Selections, Usage, buildLaunchOptions, detectSelections } from "./catalog";
import { GameEntry, readLaunchOptions, resolveLiveAppid, writeLaunchOptions } from "./steamApi";

export type SaveStatus = "saving" | "saved" | null;

export interface LaunchEditor {
  loading: boolean;
  malformed: boolean;
  raw: string;
  selections: Selections;
  /** Per-pill apply counts (drives the Frecuentes row). */
  usage: Usage;
  preview: string;
  /** Autosave state for the subtle status line (no manual button). */
  status: SaveStatus;
  /** Set a pill: boolean for toggles, a value string for value pills, null/false = off. */
  set: (id: string, value: string | boolean | null) => void;
}

const isActive = (v: string | boolean | undefined): boolean => v !== undefined && v !== false;

/**
 * Drives the launch-options editor for one game. The Steam string is the source
 * of truth: we read it once (baseline), derive active pills, and recompose on
 * every toggle. Changes AUTOSAVE (debounced) — no manual button; we write via
 * Steam's API and adopt the composed string as the new baseline (Steam's store
 * updates async, so a read-back would race). Usage is counted once per session
 * per newly-enabled pill (drives the Frecuentes row).
 */
export function useLaunchEditor(game: GameEntry, catalog: Pill[] = CATALOG): LaunchEditor {
  const [baseline, setBaseline] = useState<Parsed | null>(null);
  const [selections, setSelections] = useState<Selections>({});
  const [usage, setUsage] = useState<Usage>({});
  const [status, setStatus] = useState<SaveStatus>(null);
  const bumped = useRef<Set<string>>(new Set());
  const savedFlash = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Read the Steam string once per game (keyed only by appid — no I/O on catalog change).
  useEffect(() => {
    let cancelled = false;
    setBaseline(null);
    setStatus(null);
    bumped.current = new Set();
    readLaunchOptions(game.liveAppid).then((rawStr) => {
      if (cancelled) return;
      const p = parse(rawStr);
      // Seed baseline + selections together so the first painted frame never shows
      // every pill off (which would strip the string and arm a bogus autosave).
      setBaseline(p);
      setSelections(detectSelections(p, catalog));
    });
    return () => {
      cancelled = true;
    };
  }, [game.liveAppid]);

  // Custom pills load async — re-derive from the in-memory baseline when the catalog
  // grows (no re-read of the Steam string). No-op when it already matches.
  useEffect(() => {
    if (baseline) setSelections(detectSelections(baseline, catalog));
  }, [baseline, catalog]);

  // Usage counts are global (not per-game); load once for the Frecuentes row.
  useEffect(() => {
    let cancelled = false;
    getLaunchUsage()
      .then((u) => !cancelled && setUsage(u))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const preview = useMemo(
    () => (baseline ? buildLaunchOptions(baseline, selections, catalog) : ""),
    [baseline, selections, catalog],
  );
  const dirty = baseline ? preview !== serialize(baseline) : false;

  const set = useCallback((id: string, value: string | boolean | null) => {
    setSelections((s) => {
      const next = { ...s };
      if (value === null || value === false) delete next[id];
      else next[id] = value;
      return next;
    });
  }, []);

  // Autosave: debounce writes so rapid toggles / typing don't hammer Steam.
  useEffect(() => {
    if (!baseline || baseline.malformed || !dirty) return;
    setStatus("saving");
    const target = preview;
    const id = setTimeout(() => {
      const appid = resolveLiveAppid(game.stableKey) ?? game.liveAppid;
      writeLaunchOptions(appid, target);
      setBaseline(parse(target)); // the composed string is now the saved baseline
      // Count newly-enabled pills once per session so the Frecuentes row learns.
      const fresh = Object.keys(selections).filter((k) => isActive(selections[k]) && !bumped.current.has(k));
      if (fresh.length) {
        fresh.forEach((k) => bumped.current.add(k));
        setUsage((u) => {
          const n = { ...u };
          for (const k of fresh) n[k] = (n[k] ?? 0) + 1;
          return n;
        });
        bumpLaunchUsage(fresh).catch(() => {});
      }
      setStatus("saved");
      if (savedFlash.current) clearTimeout(savedFlash.current);
      savedFlash.current = setTimeout(() => setStatus(null), 1500);
    }, 500);
    return () => clearTimeout(id);
  }, [preview, dirty, baseline, selections, game.stableKey, game.liveAppid]);

  useEffect(() => () => {
    if (savedFlash.current) clearTimeout(savedFlash.current);
  }, []);

  return {
    loading: baseline === null,
    malformed: !!baseline?.malformed,
    raw: baseline?.raw ?? "",
    selections,
    usage,
    preview,
    status,
    set,
  };
}
