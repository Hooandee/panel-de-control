import { ButtonItem } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { LuDatabase } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { listThemeData, resetThemeData, type ThemeDataEntry } from "../themes/themeDataClient";

const CONFIRM_WINDOW_MS = 4000;

function fallbackName(catalogId: string): string {
  const bare = catalogId.replace(/^hooandee-/, "").replace(/-/g, " ");
  return bare.charAt(0).toUpperCase() + bare.slice(1);
}

// What theme runtimes keep through Panel (a home layout, folders): one row per theme, resettable.
export function ThemeDataCard({ names }: { names: Readonly<Record<string, string>> }) {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<ThemeDataEntry[]>([]);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    listThemeData().then(setEntries, () => setEntries([]));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (!confirming) return undefined;
    const timer = window.setTimeout(() => setConfirming(null), CONFIRM_WINDOW_MS);
    return () => window.clearTimeout(timer);
  }, [confirming]);

  const reset = async (catalogId: string) => {
    if (confirming !== catalogId) {
      setConfirming(catalogId);
      return;
    }
    setConfirming(null);
    setBusy(catalogId);
    const ok = await resetThemeData(catalogId).catch(() => false);
    setBusy(null);
    setFailed(!ok);
    load();
  };

  if (entries.length === 0) return null;

  return (
    <div style={{ ...theme.card, padding: theme.space.md }}>
      <div style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, display: "flex", alignItems: "center", gap: 7 }}>
        <LuDatabase size={16} color={theme.color.accent} aria-hidden /> {t("themes.data.title")}
      </div>
      <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
        {t("themes.data.description")}
      </div>
      {entries.map((entry) => (
        <div key={entry.catalogId} style={{ marginTop: theme.space.md }}>
          <div style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{names[entry.catalogId] ?? fallbackName(entry.catalogId)}</div>
          <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, marginTop: 2 }}>
            {[
              entry.summary,
              `${Math.max(1, Math.round(entry.bytes / 1024))} KB`,
              new Date(entry.updatedAt * 1000).toLocaleDateString(lang),
            ].filter(Boolean).join(" · ")}
          </div>
          <ButtonItem layout="below" disabled={busy !== null} onClick={() => void reset(entry.catalogId)}>
            {t(confirming === entry.catalogId ? "themes.data.confirm" : "themes.data.reset")}
          </ButtonItem>
        </div>
      ))}
      {failed ? <div role="alert" style={{ color: theme.color.warn, marginTop: theme.space.sm }}>{t("themes.data.failed")}</div> : null}
    </div>
  );
}
