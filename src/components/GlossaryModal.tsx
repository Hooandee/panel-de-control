import { FC } from "react";
import { ModalRoot, showModal, Focusable } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { CATEGORIES, pick } from "../glossary/data";
import { FocusRoot } from "./FocusRoot";

// Full-screen glossary. Content lives in ../glossary/data (bulky bilingual
// prose); this component is pure presentation. useI18n degrades gracefully
// outside the provider (showModal renders in its own React root), so the
// active language still resolves.
const GlossaryBody: FC = () => {
  const { t, lang } = useI18n();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg, padding: theme.space.sm, maxWidth: 720, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("glossary.title")}</div>
        <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>{t("glossary.intro")}</div>
      </div>

      {CATEGORIES.map((cat) => (
        <div key={cat.id} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={theme.sectionLabel}>
            {pick(cat, lang)}
          </div>
          {cat.terms.map((term) => (
            // Each card is Focusable so the gamepad has something to move focus
            // through — in Steam's Gamepad UI that focus movement is what
            // scrolls a long modal (a body of plain divs can't be scrolled with
            // a controller). Mirrors the Focusable rows in CustomizeModal.
            <Focusable key={term.id} style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
              <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.accent }}>{term.term}</div>
              <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.45 }}>{pick(term, lang)}</div>
            </Focusable>
          ))}
        </div>
      ))}
    </div>
  );
};

const GlossaryModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <GlossaryBody />
    </FocusRoot>
  </ModalRoot>
);

/** Open the full-screen glossary. Read-only content, so no onClose plumbing. */
export function openGlossaryModal(): void {
  showModal(<GlossaryModal />, window);
}
