import type { FC } from "react";
import { LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

export const ComingSoonCard: FC<{ image: string; imageAlt: string; title: string; body: string }> = ({ image, imageAlt, title, body }) => {
  const { t } = useI18n();
  return (
    <div style={{ ...theme.card, overflow: "hidden" }}>
      <img src={image} alt={imageAlt} style={{ display: "block", width: "100%", height: "auto" }} />
      <div style={{ padding: theme.space.md }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
          <div style={{ flex: 1, minWidth: 0, color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750 }}>{title}</div>
          <span style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            flexShrink: 0,
            padding: "3px 8px",
            borderRadius: 999,
            fontSize: theme.font.caption,
            fontWeight: 700,
            color: theme.color.accent,
            background: `rgba(${theme.color.accentRgb},0.14)`,
            boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.35)`,
          }}>
            <LuSparkles size={11} aria-hidden /> {t("comingSoon.badge")}
          </span>
        </div>
        <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>{body}</div>
      </div>
    </div>
  );
};
