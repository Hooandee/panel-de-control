import { FC, useRef } from "react";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useFloatingTrayClaim } from "./useFloatingTrayClaim";
import { stickyTrayStyle, useStickyTray } from "./useStickyTray";

interface Props {
  seconds: number;
  saving: boolean;
  onSave: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
}

const GLYPH_X = "#3d7fff";
const GLYPH_Y = "#f5c400";

const ButtonGlyph: FC<{ letter: string; color: string }> = ({ letter, color }) => (
  <span aria-hidden style={{
    flexShrink: 0, width: 16, height: 16, borderRadius: "50%", background: color,
    color: "#101010", fontSize: 10, fontWeight: 800, lineHeight: "16px", textAlign: "center",
  }}>
    {letter}
  </span>
);

// The gamepad acts through the X/Y shortcuts its section announces in Steam's footer.
// The tray never takes focus: it unmounts on save/discard, and a focused node that
// unmounts leaves Steam with no focus at all.
export const ColorPreviewConfirm: FC<Props> = ({ seconds, saving, onSave, onDiscard }) => {
  const { t } = useI18n();
  const trayRef = useRef<HTMLDivElement>(null);
  const locked = useRef(false);
  useFloatingTrayClaim(true);
  useStickyTray(trayRef);

  const actionStyle = {
    flex: "1 1 auto",
    minWidth: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    minHeight: 38,
    padding: "8px 4px",
    boxSizing: "border-box",
    borderRadius: theme.radius.sm,
    fontSize: theme.font.caption,
    fontWeight: 700,
    textAlign: "center",
    lineHeight: 1.2,
    cursor: saving ? "default" : "pointer",
    opacity: saving ? 0.55 : 1,
  } as const;
  const run = async (action: () => void | Promise<void>) => {
    if (saving || locked.current) return;
    locked.current = true;
    try {
      await action();
    } finally {
      locked.current = false;
    }
  };

  return (
    <div
      ref={trayRef}
      role="status"
      aria-live="polite"
      style={{
        ...stickyTrayStyle,
        padding: theme.space.md,
        borderRadius: theme.radius.md,
        background: theme.color.surfaceRaised,
        boxShadow: `0 10px 32px rgba(0,0,0,0.42), inset 0 0 0 1px ${theme.color.warn}`,
      }}
    >
      <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
        {t("display.confirm.title")}
      </div>
      <div style={{ marginTop: 2, fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("display.confirm.desc", { s: seconds })}
      </div>
      <div style={{ display: "flex", gap: theme.space.sm, marginTop: theme.space.sm }}>
        <div
          role="button"
          aria-label={saving ? t("display.confirm.saving") : t("display.confirm.save")}
          aria-disabled={saving}
          style={{ ...actionStyle, flexGrow: 2, background: theme.color.accent, color: "#ffffff" }}
          onClick={() => run(onSave)}
        >
          <ButtonGlyph letter="X" color={GLYPH_X} />
          {saving ? t("display.confirm.saving") : t("display.confirm.save")}
        </div>
        <div
          role="button"
          aria-label={t("display.confirm.discard")}
          aria-disabled={saving}
          style={{
            ...actionStyle,
            background: "rgba(255,255,255,0.08)",
            color: theme.color.textPrimary,
            boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          }}
          onClick={() => run(onDiscard)}
        >
          <ButtonGlyph letter="Y" color={GLYPH_Y} />
          {t("display.confirm.discard")}
        </div>
      </div>
    </div>
  );
};
