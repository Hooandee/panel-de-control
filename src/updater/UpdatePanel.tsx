import { DialogButton } from "@decky/ui";
import { useState } from "react";
import type { InstallResult } from "../api";
import { useUpdate } from "./useUpdate";

const STRINGS = {
  es: {
    version: "Versión",
    latest: "(última)",
    newPrefix: "nueva",
    checking: "buscando…",
    check: "Buscar actualizaciones",
    install: "Instalar",
    installing: "Instalando…",
    restart: "Reiniciar Decky",
    restartNote: "Reinicia Decky para aplicar la actualización.",
    changes: "Novedades",
    failed: "No se pudo instalar. Inténtalo de nuevo.",
    error: "No se pudo comprobar. Revisa tu conexión.",
  },
  en: {
    version: "Version",
    latest: "(latest)",
    newPrefix: "new",
    checking: "checking…",
    check: "Check for updates",
    install: "Install",
    installing: "Installing…",
    restart: "Restart Decky",
    restartNote: "Restart Decky to apply the update.",
    changes: "What's new",
    failed: "Install failed. Please try again.",
    error: "Couldn't check. Check your connection.",
  },
} as const;

const MUTED = "rgba(255,255,255,0.55)";

// Inline update UI (no PanelSection wrapper): a single unified version line +
// a button below it. Host owns any surrounding chrome (title, author credit).
// `version` gives the installed version instantly, before the async check lands.
export function UpdatePanel({ lang, version }: { lang: "es" | "en"; version?: string }) {
  const t = STRINGS[lang];
  const { info, status, check, install, restart } = useUpdate(lang);
  const [result, setResult] = useState<InstallResult | null>(null);

  const current = info?.current ?? version ?? "";
  const hasUpdate = !!info?.has_update;
  const busy = status === "checking" || status === "installing";

  let suffix = "";
  if (status === "checking") suffix = ` · ${t.checking}`;
  else if (hasUpdate) suffix = ` · ${t.newPrefix} v${info?.latest}`;
  else if (status !== "error") suffix = ` ${t.latest}`;

  let label: string = status === "checking" ? t.checking : t.check;
  let onClick: () => void = () => void check();
  if (status === "done") {
    label = t.restart;
    onClick = () => restart();
  } else if (hasUpdate) {
    label = status === "installing" ? t.installing : `${t.install} v${info?.latest}`;
    onClick = () => void install().then(setResult);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
        {t.version} {current || "…"}
        {suffix}
      </div>

      {status === "error" && !hasUpdate && (
        <div style={{ fontSize: 11, color: MUTED }}>{t.error}</div>
      )}

      {hasUpdate && !!info?.notes && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: MUTED, marginBottom: 2 }}>
            {t.changes}
          </div>
          <div
            style={{
              fontSize: 11,
              color: MUTED,
              whiteSpace: "pre-wrap",
              maxHeight: 180,
              overflowY: "auto",
            }}
          >
            {info.notes}
          </div>
        </div>
      )}

      {status === "done" && <div style={{ fontSize: 11, color: MUTED }}>{t.restartNote}</div>}
      {result && !result.ok && <div style={{ fontSize: 11, color: "#ff6b6b" }}>{t.failed}</div>}

      <DialogButton
        disabled={busy}
        onClick={onClick}
        style={{ width: "100%", padding: "6px 12px", fontSize: 13, minWidth: 0 }}
      >
        {label}
      </DialogButton>
    </div>
  );
}
