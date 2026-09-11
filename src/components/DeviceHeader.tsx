import { FC } from "react";
import { DeviceInfo, isUnvalidated } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

export const DeviceHeader: FC<{ device: DeviceInfo }> = ({ device }) => {
  const { t } = useI18n();
  return (
    <div
      data-testid="device-pill"
      style={{
        display: "inline-flex",
        alignItems: "center",
        alignSelf: "flex-start",
        gap: 6,
        width: "fit-content",
        maxWidth: "100%",
        minHeight: 24,
        padding: "3px 8px",
        borderRadius: 999,
        background: "rgba(255,255,255,0.04)",
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        boxSizing: "border-box",
      }}
    >
      <span
        style={{
          minWidth: 0,
          color: theme.color.textPrimary,
          fontSize: theme.font.caption,
          fontWeight: 650,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {t("device.detected", { name: device.display_name })}
      </span>
      <span aria-hidden="true" style={{ color: theme.color.textMuted, fontSize: 9 }}>•</span>
      <span
        style={{
          flexShrink: 0,
          color: theme.color.textMuted,
          fontSize: 9,
          fontWeight: 650,
          letterSpacing: "0.05em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        {device.chip}
      </span>
      {isUnvalidated(device) && (
        <span
          role="img"
          aria-label={t(device.is_generic ? "device.generic.hint" : "device.experimental.hint")}
          title={t(device.is_generic ? "device.generic.hint" : "device.experimental.hint")}
          style={{
            width: 6,
            height: 6,
            flexShrink: 0,
            borderRadius: "50%",
            background: theme.color.warn,
          }}
        />
      )}
    </div>
  );
};
