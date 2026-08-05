import { FC } from "react";
import { DialogButton } from "@decky/ui";
import {
  LuArrowLeft,
  LuArrowRight,
  LuArrowUpLeft,
  LuArrowUpRight,
  LuCircleDot,
  LuGamepad2,
  LuSparkles,
  LuVibrate,
} from "react-icons/lu";

import { theme } from "../theme";
import { CompactFieldSurface } from "../components/CompactField";
import type { ControllerVibrationTestChannel } from "../api";

export type VibrationTestChannel = ControllerVibrationTestChannel;

interface Props {
  channels: readonly VibrationTestChannel[];
  disabled: boolean;
  selectLabel: string;
  description?: string;
  buttonLabel: string;
  channelLabel: (channel: VibrationTestChannel) => string;
  channelStrength?: (channel: VibrationTestChannel) => number | null;
  onTest: (channel: VibrationTestChannel, strength: number) => void;
}

const ChannelIcon: FC<{ channel: VibrationTestChannel }> = ({ channel }) => {
  const iconProps = { size: 17, "aria-hidden": true, focusable: false } as const;
  if (channel === "left") return <LuArrowLeft {...iconProps} />;
  if (channel === "right") return <LuArrowRight {...iconProps} />;
  if (channel === "trigger_left") return <LuArrowUpLeft {...iconProps} />;
  if (channel === "trigger_right") return <LuArrowUpRight {...iconProps} />;
  if (channel === "strong") return <LuCircleDot {...iconProps} />;
  if (channel === "weak") return <LuSparkles {...iconProps} />;
  if (channel === "all") return <LuGamepad2 {...iconProps} />;
  return <LuVibrate {...iconProps} />;
};

export const VibrationTestControl: FC<Props> = ({
  channels, disabled, selectLabel, description, buttonLabel, channelLabel,
  channelStrength, onTest,
}) => {
  if (channels.length === 0) return null;

  return (
    <CompactFieldSurface>
      <div style={{ marginBottom: theme.space.xs, color: theme.color.textPrimary, fontSize: theme.font.caption }}>
        {selectLabel}
      </div>
      {description && (
        <div style={{
          marginBottom: theme.space.sm,
          color: theme.color.textMuted,
          fontSize: theme.font.caption,
          lineHeight: 1.4,
        }}>
          {description}
        </div>
      )}
      <div style={{ display: "grid", gap: theme.space.xs }}>
        {channels.map((channel) => {
          const label = channelLabel(channel);
          const configuredStrength = channelStrength?.(channel) ?? null;
          const strength = configuredStrength ?? 50;
          const channelDisabled = disabled || strength === 0;
          return (
            <DialogButton
              key={channel}
              data-testid={`vibration-test-${channel}`}
              aria-label={`${buttonLabel}: ${label}${configuredStrength == null ? "" : `, ${configuredStrength}%`}`}
              disabled={channelDisabled}
              style={{
                width: "100%",
                minWidth: 0,
                minHeight: 40,
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-start",
                gap: theme.space.sm,
                whiteSpace: "nowrap",
                overflow: "hidden",
              }}
              onClick={() => onTest(channel, strength)}
            >
              <span style={{ display: "inline-flex", flexShrink: 0, color: theme.color.accent }}>
                <ChannelIcon channel={channel} />
              </span>
              <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
                {label}
              </span>
              {configuredStrength != null && (
                <span style={{
                  marginLeft: "auto",
                  flexShrink: 0,
                  whiteSpace: "nowrap",
                  color: strength === 0 ? theme.color.textMuted : theme.color.textPrimary,
                  fontSize: theme.font.caption,
                  fontWeight: 700,
                }}>
                  {configuredStrength}%
                </span>
              )}
            </DialogButton>
          );
        })}
      </div>
    </CompactFieldSurface>
  );
};
