import { FC, useRef } from "react";
import { Focusable } from "@decky/ui";
import { LuCheck, LuUndo2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  seconds: number;
  saving: boolean;
  onSave: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
}

export const ColorPreviewConfirm: FC<Props> = ({ seconds, saving, onSave, onDiscard }) => {
  const { t } = useI18n();
  const locked = useRef(false);
  const actionStyle = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    minHeight: 38,
    padding: "8px 12px",
    borderRadius: theme.radius.sm,
    fontSize: theme.font.body,
    fontWeight: 700,
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
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        right: theme.space.md,
        bottom: 64,
        zIndex: 1000,
        width: "min(390px, calc(100vw - 32px))",
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
        <Focusable
          role="button"
          aria-label={saving ? t("display.confirm.saving") : t("display.confirm.save")}
          aria-disabled={saving}
          style={{
            ...actionStyle,
            flex: 1,
            background: theme.color.accent,
            color: "#ffffff",
          }}
          onActivate={() => run(onSave)}
          onClick={() => run(onSave)}
        >
          <LuCheck size={16} />
          {saving ? t("display.confirm.saving") : t("display.confirm.save")}
        </Focusable>
        <Focusable
          role="button"
          aria-label={t("display.confirm.discard")}
          aria-disabled={saving}
          style={{
            ...actionStyle,
            background: "rgba(255,255,255,0.08)",
            color: theme.color.textPrimary,
            boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          }}
          onActivate={() => run(onDiscard)}
          onClick={() => run(onDiscard)}
        >
          <LuUndo2 size={15} />
          {t("display.confirm.discard")}
        </Focusable>
      </div>
    </div>
  );
};
