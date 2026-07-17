import { FC } from "react";
import { Focusable } from "@decky/ui";
import { LuTriangleAlert } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface RivalRowProps {
  name: string;
  desc: string;
  action: string;
  onAction: () => void;
}

const RivalRow: FC<RivalRowProps> = ({ name, desc, action, onAction }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: theme.space.sm,
      marginTop: theme.space.sm,
      padding: `${theme.space.sm}px ${theme.space.md}px`,
      borderRadius: theme.radius.sm,
      background: theme.color.surface,
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    <div style={{ flex: "1 1 auto", minWidth: 0 }}>
      <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
        {name}
      </div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{desc}</div>
    </div>
    <Focusable
      onActivate={onAction}
      onClick={onAction}
      noFocusRing
      style={{
        flex: "0 0 auto",
        padding: `${theme.space.sm}px ${theme.space.md}px`,
        borderRadius: theme.radius.sm,
        background: theme.color.accent,
        color: theme.color.onAccent,
        fontSize: theme.font.body,
        fontWeight: 650,
        whiteSpace: "nowrap",
      }}
    >
      {action}
    </Focusable>
  </div>
);

interface Props {
  rivals: { sdtdp: boolean; hhd: boolean };
  onDisableSdtdp: () => void;
  onTakeHhd: () => void;
}

/**
 * Permanent conflict card shown atop Potencia while another TDP manager is active
 * (after the user dismissed the first-run modal, or if a rival reappears). One row
 * per active rival with a reversible action. Deliberately persistent — it nags.
 */
export const TdpConflictCard: FC<Props> = ({ rivals, onDisableSdtdp, onTakeHhd }) => {
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
        <LuTriangleAlert size={16} color={theme.color.warn} /> {t("tdp.conflict.card.title")}
      </div>
      <div
        style={{
          fontSize: theme.font.caption,
          color: theme.color.textMuted,
          marginTop: theme.space.xs,
          lineHeight: 1.4,
        }}
      >
        {t("tdp.conflict.card.desc")}
      </div>
      {rivals.sdtdp && (
        <RivalRow
          name={t("tdp.conflict.sdtdp")}
          desc={t("tdp.conflict.sdtdp.desc")}
          action={t("tdp.conflict.disable")}
          onAction={onDisableSdtdp}
        />
      )}
      {rivals.hhd && (
        <RivalRow
          name={t("tdp.conflict.hhd")}
          desc={t("tdp.conflict.hhd.desc")}
          action={t("tdp.conflict.cede")}
          onAction={onTakeHhd}
        />
      )}
    </div>
  );
};
