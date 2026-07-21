import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toaster } from "@decky/api";

import { bumpLaunchUsage, getLaunchUsage } from "../api";
import { translate } from "../i18n";
import { Parsed, parse, serialize } from "./compose";
import { AMBIGUOUS, CATALOG, Pill, Selections, Usage, buildLaunchOptions, detectSelections } from "./catalog";
import { GameEntry, readAppDetails, writeLaunchOptions } from "./steamApi";

export type SaveStatus = "saving" | "saved" | "error" | null;

export interface LaunchEditor {
  loading: boolean;
  /** The Steam string couldn't be read — do not edit (a write would erase it). */
  error: boolean;
  malformed: boolean;
  raw: string;
  /** Proton compat tool id + label for this game ("" when native / none). Read from
   *  the same details callback so Proton gating doesn't depend on a warm cache. */
  compatName: string;
  compatDisplay: string;
  selections: Selections;
  /** Per-pill apply counts (drives the Frecuentes row). */
  usage: Usage;
  preview: string;
  /** Autosave state for the subtle status line (no manual button). */
  status: SaveStatus;
  /** Set a pill: boolean for toggles, a value string for value pills, null/false = off. */
  set: (id: string, value: string | boolean | null) => void;
}

const isActive = (v: string | boolean | undefined): boolean => v !== undefined && v !== false && v !== AMBIGUOUS;

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
  const [error, setError] = useState(false);
  const [compat, setCompat] = useState<{ name: string; display: string }>({ name: "", display: "" });
  const [selections, setSelections] = useState<Selections>({});
  const [usage, setUsage] = useState<Usage>({});
  const [status, setStatus] = useState<SaveStatus>(null);
  const bumped = useRef<Set<string>>(new Set());
  const savedFlash = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Target awaiting an autosave write (null = nothing pending) — flushed on unmount
  // so closing the modal before the debounce fires doesn't silently drop the change.
  const pending = useRef<string | null>(null);

  // Read the Steam string once per game (keyed only by appid — no I/O on catalog change).
  useEffect(() => {
    let cancelled = false;
    setBaseline(null);
    setError(false);
    setStatus(null);
    bumped.current = new Set();
    readAppDetails(game.liveAppid).then((d) => {
      if (cancelled) return;
      // null = couldn't read → error, don't fabricate an empty baseline (a write
      // from "" would erase the user's real options).
      if (d === null) {
        setError(true);
        return;
      }
      const p = parse(d.launch);
      // Seed baseline + selections together so the first painted frame never shows
      // every pill off (which would strip the string and arm a bogus autosave).
      setBaseline(p);
      setSelections(detectSelections(p, catalog));
      setCompat({ name: d.compatName, display: d.compatDisplay });
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

  // Autosave: debounce writes so rapid toggles / typing don't hammer Steam. Baseline,
  // usage and "saved" are adopted ONLY when the write actually succeeds — a missing
  // or throwing setter surfaces as "error", never a fake "Saved".
  useEffect(() => {
    if (!baseline || baseline.malformed || !dirty) return;
    setStatus("saving");
    const target = preview;
    pending.current = target;
    const id = setTimeout(() => {
      // Write to the appid we opened + read from — never re-resolve by name (two
      // non-Steam shortcuts can share a name → wrong game), and no library rescan.
      const appid = game.liveAppid;
      if (!writeLaunchOptions(appid, target, game.isNonSteam)) {
        setStatus("error"); // keep `pending` so the unmount flush can retry
        return;
      }
      pending.current = null;
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
  }, [preview, dirty, baseline, selections, game.stableKey, game.liveAppid, game.isNonSteam]);

  // Flush a pending change on unmount (closing before the 500ms debounce fired).
  // The modal is per-game, so mount-time game identity is correct here.
  useEffect(
    () => () => {
      if (savedFlash.current) clearTimeout(savedFlash.current);
      if (pending.current !== null && !writeLaunchOptions(game.liveAppid, pending.current, game.isNonSteam)) {
        // The modal is gone — surface the lost change with a toast, don't swallow it.
        toaster.toast({ title: game.name, body: translate("params.saveError") });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return {
    loading: baseline === null && !error,
    error,
    malformed: !!baseline?.malformed,
    raw: baseline?.raw ?? "",
    compatName: compat.name,
    compatDisplay: compat.display,
    selections,
    usage,
    preview,
    status,
    set,
  };
}
