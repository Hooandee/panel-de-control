import { FC, useRef } from "react";
import { Focusable } from "@decky/ui";
import { LuActivity } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  onReactivate?: () => void | Promise<void>;
}

// Shown in Potencia when the TDP master switch is off: only the live arc plus a
// button to turn control back on.
export const TdpMonitorNotice: FC<Props> = ({ onReactivate }) => {
  const { t } = useI18n();
  // Focusable fires onActivate AND onClick; guard for the whole write so one press
  // isn't two RPCs. Released when it settles so a later retry works.
  const busy = useRef(false);
  const reactivate = () => {
    if (busy.current || !onReactivate) return;
    busy.current = true;
    Promise.resolve()
      .then(() => onReactivate())
      .finally(() => { busy.current = false; });
  };
  return (
    <div
      style={{
        ...theme.card,
        padding: theme.space.md,
        display: "flex",
        flexDirection: "column",
        gap: theme.space.sm,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, fontSize: theme.font.body, color: theme.color.textMuted }}>
        <LuActivity size={16} color={theme.color.textMuted} style={{ flex: "0 0 auto" }} />
        {t("tdp.monitor.notice")}
      </div>
      {onReactivate && (
        <Focusable
          onActivate={reactivate}
          onClick={reactivate}
          noFocusRing
          style={{
            alignSelf: "flex-start",
            padding: `${theme.space.sm}px ${theme.space.md}px`,
            borderRadius: theme.radius.sm,
            background: theme.color.accent,
            color: theme.color.onAccent,
            fontSize: theme.font.body,
            fontWeight: 650,
            whiteSpace: "nowrap",
          }}
        >
          {t("tdp.monitor.reactivate")}
        </Focusable>
      )}
    </div>
  );
};
