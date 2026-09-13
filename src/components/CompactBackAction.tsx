import { Focusable } from "@decky/ui";
import { useRef } from "react";
import { LuChevronLeft } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

export interface CompactBackActionProps {
  onBack: () => void;
  label?: string;
}

export function CompactBackAction({ onBack, label }: CompactBackActionProps) {
  const { t } = useI18n();
  const text = label ?? t("home.back");
  const locked = useRef(false);
  const goBack = () => {
    if (locked.current) return;
    locked.current = true;
    try {
      onBack();
    } finally {
      queueMicrotask(() => { locked.current = false; });
    }
  };

  return (
    <Focusable
      role="button"
      aria-label={text}
      onActivate={goBack}
      onClick={goBack}
      style={{
        minHeight: 28,
        display: "inline-flex",
        alignItems: "center",
        flexShrink: 0,
        gap: theme.space.xs,
        padding: `0 ${theme.space.xs}px`,
        color: theme.color.textMuted,
        cursor: "pointer",
      }}
    >
      <LuChevronLeft size={18} aria-hidden="true" />
      <span style={{ fontSize: theme.font.caption, fontWeight: 600 }}>{text}</span>
    </Focusable>
  );
}
