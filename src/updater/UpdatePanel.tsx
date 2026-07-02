import { DialogButton, showModal } from "@decky/ui";
import { useUpdate } from "./useUpdate";
import { UpdateModal } from "./UpdateModal";

const STRINGS = {
  es: {
    version: "Versión",
    latest: "(última)",
    newPrefix: "nueva",
    checking: "buscando…",
    check: "Buscar actualizaciones",
    update: "Ver novedades e instalar",
    error: "No se pudo comprobar. Revisa tu conexión.",
  },
  en: {
    version: "Version",
    latest: "(latest)",
    newPrefix: "new",
    checking: "checking…",
    check: "Check for updates",
    update: "See what's new & install",
    error: "Couldn't check. Check your connection.",
  },
} as const;

const MUTED = "rgba(255,255,255,0.55)";

// Inline: a single unified version line + one button. The changelog and the
// install action live in a modal (opened when an update is available).
export function UpdatePanel({ lang, version }: { lang: "es" | "en"; version?: string }) {
  const t = STRINGS[lang];
  const { info, status, check } = useUpdate(lang);

  const current = info?.current ?? version ?? "";
  const hasUpdate = !!info?.has_update;
  const busy = status === "checking" || status === "installing";

  let suffix = "";
  if (status === "checking") suffix = ` · ${t.checking}`;
  else if (hasUpdate) suffix = ` · ${t.newPrefix} v${info?.latest}`;
  else if (status !== "error") suffix = ` ${t.latest}`;

  const onClick = () => {
    if (info?.has_update) {
      showModal(<UpdateModal lang={lang} latest={info.latest} notes={info.notes} />);
    } else {
      void check();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
        {t.version} {current || "…"}
        {suffix}
      </div>
      {status === "error" && !hasUpdate && <div style={{ fontSize: 11, color: MUTED }}>{t.error}</div>}
      <DialogButton
        disabled={busy}
        onClick={onClick}
        style={{ width: "100%", padding: "6px 12px", fontSize: 13, minWidth: 0 }}
      >
        {hasUpdate ? t.update : status === "checking" ? t.checking : t.check}
      </DialogButton>
    </div>
  );
}
