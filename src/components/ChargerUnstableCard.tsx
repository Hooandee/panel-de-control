import { FC } from "react";
import { Focusable } from "@decky/ui";
import { LuPlugZap } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  transitions: number;
  onDismiss: () => void;
}

export const ChargerUnstableCard: FC<Props> = ({ transitions, onDismiss }) => {
  const { t } = useI18n();
  return (
    <div
      style={{
        ...theme.card,
        padding: theme.space.md,
        marginTop: theme.space.section,
        marginBottom: theme.space.sm,
        overflow: "hidden",
        boxShadow: `inset 0 0 0 1px ${theme.color.warn}55`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: theme.space.xs,
          fontSize: theme.font.body,
          fontWeight: 700,
          color: theme.color.warn,
        }}
      >
        <LuPlugZap size={16} color={theme.color.warn} /> {t("tdp.charger.title")}
      </div>
      <div
        style={{
          fontSize: theme.font.caption,
          color: theme.color.textMuted,
          marginTop: theme.space.xs,
          lineHeight: 1.4,
        }}
      >
        {t("tdp.charger.desc", { n: transitions })}
      </div>
      <Focusable
        onActivate={onDismiss}
        onClick={onDismiss}
        noFocusRing
        style={{
          marginTop: theme.space.sm,
          padding: `${theme.space.sm}px ${theme.space.md}px`,
          borderRadius: theme.radius.sm,
          background: theme.color.surface,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          color: theme.color.textPrimary,
          fontSize: theme.font.body,
          fontWeight: 650,
          textAlign: "center",
        }}
      >
        {t("tdp.charger.dismiss")}
      </Focusable>
    </div>
  );
};
