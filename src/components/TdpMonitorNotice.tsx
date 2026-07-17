import { FC } from "react";
import { LuActivity } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

// Banner shown in Potencia when we're not controlling TDP (no backend, or master
// switch off). The section shows only the live arc alongside it.
export const TdpMonitorNotice: FC = () => {
  const { t } = useI18n();
  return (
    <div
      style={{
        ...theme.card,
        padding: theme.space.md,
        display: "flex",
        alignItems: "center",
        gap: theme.space.sm,
        fontSize: theme.font.body,
        color: theme.color.textMuted,
      }}
    >
      <LuActivity size={16} color={theme.color.textMuted} style={{ flex: "0 0 auto" }} />
      {t("tdp.monitor.notice")}
    </div>
  );
};
