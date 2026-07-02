import { DialogButton, ModalRoot } from "@decky/ui";
import { type ReactNode, useState } from "react";
import type { InstallResult } from "../api";
import { useUpdate } from "./useUpdate";

const STRINGS = {
  es: {
    title: "Novedades",
    noNotes: "Sin notas para esta versión.",
    install: "Instalar actualización",
    installing: "Instalando…",
    installed: "Actualización instalada.",
    restartNote: "Reinicia Decky para aplicarla.",
    restart: "Reiniciar Decky",
    failed: "No se pudo instalar. Inténtalo de nuevo.",
  },
  en: {
    title: "What's new",
    noNotes: "No notes for this release.",
    install: "Install update",
    installing: "Installing…",
    installed: "Update installed.",
    restartNote: "Restart Decky to apply it.",
    restart: "Restart Decky",
    failed: "Install failed. Please try again.",
  },
} as const;

const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

// Inline markdown: [text](url) -> text, **bold**, `code`.
function renderInline(text: string): ReactNode[] {
  const noLinks = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  return noLinks.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <b key={i}>{p.slice(2, -2)}</b>;
    if (p.startsWith("`") && p.endsWith("`")) {
      return (
        <code key={i} style={{ fontFamily: MONO, fontSize: "0.9em", opacity: 0.9 }}>
          {p.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{p}</span>;
  });
}

// Minimal block renderer for the markdown release-please produces:
// ## / ### headings, `* ` / `- ` bullet lists, and paragraphs.
function renderMarkdown(md: string): ReactNode[] {
  const out: ReactNode[] = [];
  let bullets: ReactNode[] = [];
  const flush = (key: string) => {
    if (bullets.length) {
      out.push(
        <ul key={key} style={{ margin: "4px 0", paddingLeft: 20 }}>
          {bullets}
        </ul>,
      );
      bullets = [];
    }
  };
  md.replace(/\r/g, "").split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    const bullet = line.match(/^[*-]\s+(.*)$/);
    if (heading) {
      flush(`u${i}`);
      out.push(
        <div
          key={i}
          style={{ fontSize: heading[1].length <= 2 ? 16 : 13, fontWeight: 700, margin: "12px 0 4px" }}
        >
          {renderInline(heading[2])}
        </div>,
      );
    } else if (bullet) {
      bullets.push(
        <li key={i} style={{ fontSize: 12, margin: "3px 0", lineHeight: 1.35 }}>
          {renderInline(bullet[1])}
        </li>,
      );
    } else if (line.trim() === "") {
      flush(`u${i}`);
    } else {
      flush(`u${i}`);
      out.push(
        <div key={i} style={{ fontSize: 12, margin: "4px 0", lineHeight: 1.4 }}>
          {renderInline(line)}
        </div>,
      );
    }
  });
  flush("uend");
  return out;
}

export function UpdateModal({
  lang,
  latest,
  notes,
  closeModal,
}: {
  lang: "es" | "en";
  latest: string;
  notes: string;
  closeModal?: () => void;
}) {
  const t = STRINGS[lang];
  const { install, restart, status } = useUpdate(lang);
  const [result, setResult] = useState<InstallResult | null>(null);
  const installing = status === "installing";
  const done = status === "done";

  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>
          {t.title} v{latest}
        </div>
        <div style={{ maxHeight: 340, overflowY: "auto", paddingRight: 8 }}>
          {notes ? renderMarkdown(notes) : <div style={{ opacity: 0.7 }}>{t.noNotes}</div>}
        </div>
        {done ? (
          <>
            <div style={{ fontSize: 13 }}>
              {t.installed} {t.restartNote}
            </div>
            <DialogButton onClick={() => restart()}>{t.restart}</DialogButton>
          </>
        ) : (
          <DialogButton disabled={installing} onClick={() => void install().then(setResult)}>
            {installing ? t.installing : t.install}
          </DialogButton>
        )}
        {result && !result.ok && (
          <div style={{ fontSize: 12, color: "#ff6b6b" }}>{t.failed}</div>
        )}
      </div>
    </ModalRoot>
  );
}
