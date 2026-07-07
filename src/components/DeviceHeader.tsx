import { FC } from "react";
import { DeviceInfo, isUnvalidated } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

export const DeviceHeader: FC<{ device: DeviceInfo }> = ({ device }) => {
  const { t } = useI18n();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: theme.space.md,
        padding: `${theme.space.md}px ${theme.space.lg}px`,
        borderRadius: theme.radius.md,
        background:
          "radial-gradient(120% 90% at 0% 0%, rgba(78,161,255,0.10), rgba(0,0,0,0) 60%), " +
          theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div
          style={{
            fontSize: theme.font.body,
            fontWeight: 600,
            color: theme.color.textPrimary,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {t("device.detected", { name: device.display_name })}
        </div>
        <div
          style={{
            fontSize: theme.font.caption,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: theme.color.textMuted,
          }}
        >
          {device.chip}
        </div>
      </div>
      {isUnvalidated(device) && (
        <span
          title={t(device.is_generic ? "device.generic.hint" : "device.experimental.hint")}
          style={{
            flexShrink: 0,
            fontSize: theme.font.caption,
            padding: "2px 8px",
            borderRadius: theme.radius.sm,
            color: theme.color.warn,
            background: "rgba(255,180,84,0.12)",
          }}
        >
          {t("device.experimental.badge")}
        </span>
      )}
    </div>
  );
};
