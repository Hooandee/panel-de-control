import { useEffect, useState } from "react";

import { getThemePatchLabels } from "../api";
import { parseThemePatchLabels, type ThemePatchLabels } from "./themePatchLabels";

const NO_LABELS: ThemePatchLabels = Object.freeze({});

export function useThemePatchLabels(catalogId: string, cssLoaderName: string | undefined, version: string | undefined): ThemePatchLabels {
  const [labels, setLabels] = useState<ThemePatchLabels>(NO_LABELS);
  useEffect(() => {
    setLabels(NO_LABELS);
    if (!cssLoaderName || !version) return undefined;
    let current = true;
    getThemePatchLabels(catalogId, cssLoaderName)
      .then((value) => { if (current) setLabels(parseThemePatchLabels(value)); })
      .catch(() => {});
    return () => { current = false; };
  }, [catalogId, cssLoaderName, version]);
  return labels;
}
