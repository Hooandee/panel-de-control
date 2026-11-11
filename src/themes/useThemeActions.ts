import { useEffect, useState } from "react";

import { getThemeActions } from "../api";
import { parseThemeActions, type ThemeAction } from "./themeActions";

const NO_ACTIONS: readonly ThemeAction[] = Object.freeze([]);

export function useThemeActions(catalogId: string, cssLoaderName: string | undefined, version: string | undefined): readonly ThemeAction[] {
  const [actions, setActions] = useState<readonly ThemeAction[]>(NO_ACTIONS);
  useEffect(() => {
    setActions(NO_ACTIONS);
    if (!cssLoaderName || !version) return undefined;
    let current = true;
    getThemeActions(catalogId, cssLoaderName)
      .then((value) => { if (current) setActions(parseThemeActions(value)); })
      .catch(() => {});
    return () => { current = false; };
  }, [catalogId, cssLoaderName, version]);
  return actions;
}
