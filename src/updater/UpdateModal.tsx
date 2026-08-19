import {
  DialogButton,
  Focusable,
  GamepadButton,
  getFocusNavController,
  ModalRoot,
  type GamepadEvent,
} from "@decky/ui";
import { FocusRoot } from "../components/FocusRoot";
import { type ReactNode, useRef, useState } from "react";
import type { InstallResult } from "../api";
import { useUpdate } from "./useUpdate";
import type { Lang } from "../i18n";
import { getUpdaterStrings } from "./strings";
import { releaseNotesForLanguage } from "./releaseNotes";

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
          role="heading"
          aria-level={heading[1].length}
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
  lang: Lang;
  latest: string;
  notes: string;
  closeModal?: () => void;
}) {
  const t = getUpdaterStrings(lang).modal;
  const { install, restart, status } = useUpdate(lang);
  const [result, setResult] = useState<InstallResult | null>(null);
  const notesRef = useRef<HTMLDivElement>(null);
  const actionRef = useRef<HTMLDivElement>(null);
  const installing = status === "installing";
  const done = status === "done";
  const visibleNotes = releaseNotesForLanguage(notes, lang);

  const scrollNotes = (event: GamepadEvent) => {
    const viewport = notesRef.current;
    if (!viewport) return;
    const direction = event.detail.button === GamepadButton.DIR_DOWN
      ? 1
      : event.detail.button === GamepadButton.DIR_UP
        ? -1
        : 0;
    const atEdge = direction < 0
      ? viewport.scrollTop <= 0
      : viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 1;
    if (!direction) return;
    if (direction > 0 && atEdge) {
      getFocusNavController()?.FocusElement(actionRef.current);
      return;
    }
    if (atEdge) return;
    event.preventDefault();
    event.stopPropagation();
    viewport.scrollBy({ top: direction * viewport.clientHeight * 0.8 });
  };

  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <FocusRoot style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>
          {t.title} v{latest}
        </div>
        {visibleNotes ? (
          <Focusable onActivate={() => {}} onGamepadDirection={scrollNotes} noFocusRing>
            <div
              ref={notesRef}
              data-testid="notes-scroll"
              style={{ maxHeight: 340, overflowY: "auto", paddingRight: 8 }}
            >
              {renderMarkdown(visibleNotes)}
            </div>
          </Focusable>
        ) : (
          <div style={{ opacity: 0.7 }}>{t.noNotes}</div>
        )}
        {done ? (
          <>
            <div style={{ fontSize: 13 }}>
              {t.installed} {t.restartNote}
            </div>
            <DialogButton ref={actionRef} onClick={() => restart()}>{t.restart}</DialogButton>
          </>
        ) : (
          <DialogButton
            ref={actionRef}
            disabled={installing}
            onClick={() => void install().then(setResult)}
          >
            {installing ? t.installing : t.install}
          </DialogButton>
        )}
        {result && !result.ok && (
          <div style={{ fontSize: 12, color: "#ff6b6b" }}>{t.failed}</div>
        )}
      </FocusRoot>
    </ModalRoot>
  );
}
