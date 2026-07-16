import { useCallback, useEffect, useMemo, useState } from "react";

import { Parsed, parse, serialize } from "./compose";
import { Selections, buildLaunchOptions, detectSelections } from "./catalog";
import { GameEntry, readLaunchOptions, resolveLiveAppid, writeLaunchOptions } from "./steamApi";

export interface LaunchEditor {
  loading: boolean;
  malformed: boolean;
  raw: string;
  selections: Selections;
  preview: string;
  dirty: boolean;
  /** "ok" briefly after a successful apply, else null. */
  result: "ok" | null;
  /** Set a pill: boolean for toggles, a value string for value pills, null/false = off. */
  set: (id: string, value: string | boolean | null) => void;
  apply: () => void;
}

/**
 * Drives the launch-options editor for one game. The Steam string is the source
 * of truth: we read it once (baseline), derive active pills, and recompose on
 * every toggle. Nothing is written until apply(); apply writes via Steam's API
 * and adopts the composed string as the new baseline (Steam's store updates
 * asynchronously, so a read-back here would race and can't confirm reliably).
 */
export function useLaunchEditor(game: GameEntry): LaunchEditor {
  const [baseline, setBaseline] = useState<Parsed | null>(null);
  const [selections, setSelections] = useState<Selections>({});
  const [result, setResult] = useState<"ok" | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBaseline(null);
    setResult(null);
    readLaunchOptions(game.liveAppid).then((rawStr) => {
      if (cancelled) return;
      const p = parse(rawStr);
      setBaseline(p);
      setSelections(detectSelections(p));
    });
    return () => {
      cancelled = true;
    };
  }, [game.liveAppid]);

  const preview = useMemo(
    () => (baseline ? buildLaunchOptions(baseline, selections) : ""),
    [baseline, selections],
  );
  const dirty = useMemo(
    () => (baseline ? preview !== serialize(baseline) : false),
    [preview, baseline],
  );

  const set = useCallback((id: string, value: string | boolean | null) => {
    setResult(null);
    setSelections((s) => {
      const next = { ...s };
      if (value === null || value === false) delete next[id];
      else next[id] = value;
      return next;
    });
  }, []);

  const apply = useCallback(() => {
    if (!baseline || baseline.malformed) return;
    const target = buildLaunchOptions(baseline, selections);
    // Resolve the live appid fresh (a non-Steam shortcut's may have churned).
    const appid = resolveLiveAppid(game.stableKey) ?? game.liveAppid;
    writeLaunchOptions(appid, target);
    setBaseline(parse(target)); // the composed string is now the saved baseline
    setResult("ok");
  }, [baseline, selections, game.stableKey, game.liveAppid]);

  return {
    loading: baseline === null,
    malformed: !!baseline?.malformed,
    raw: baseline?.raw ?? "",
    selections,
    preview,
    dirty,
    result,
    set,
    apply,
  };
}
