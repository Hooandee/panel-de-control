import { FC } from "react";

import { theme } from "../theme";
import { useI18n } from "../i18n";

/**
 * The composed launch-options string, monospace. Our active tokens show in the
 * accent color; pre-existing (preserved, e.g. EmuDeck) content stays muted, so
 * it's clear what we add vs what was already there. %command% is neutral.
 */
export const LaunchPreview: FC<{ preview: string; owned: Set<string> }> = ({ preview, owned }) => {
  const { t } = useI18n();
  const tokens = preview.split(/\s+/).filter(Boolean);
  return (
    <div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginBottom: theme.space.xs }}>
        {t("params.preview")}
      </div>
      <div
        style={{
          ...theme.card,
          padding: theme.space.md,
          fontFamily: "monospace",
          fontSize: theme.font.caption,
          lineHeight: 1.7,
          wordBreak: "break-all",
        }}
      >
        {tokens.length === 0 ? (
          <span style={{ color: theme.color.textMuted, fontStyle: "italic" }}>{t("params.preview.empty")}</span>
        ) : (
          tokens.map((tok, i) => {
            const color =
              tok === "%command%"
                ? theme.color.textPrimary
                : owned.has(tok)
                  ? theme.color.accent
                  : theme.color.textMuted;
            return (
              <span key={i} style={{ color }}>
                {tok}
                {i < tokens.length - 1 ? " " : ""}
              </span>
            );
          })
        )}
      </div>
      <div style={{ display: "flex", gap: theme.space.md, marginTop: theme.space.xs, fontSize: 10, color: theme.color.textMuted }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: theme.color.textMuted, display: "inline-block" }} />
          {t("params.preview.preserved")}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: theme.color.accent, display: "inline-block" }} />
          {t("params.preview.added")}
        </span>
      </div>
    </div>
  );
};
