import { FC } from "react";
import { Focusable } from "@decky/ui";
import { LuPause, LuSparkles } from "react-icons/lu";

import { LearningStatus } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { learningBadge, LearningTag } from "../learning/logic";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";

interface Props {
  /** Foreground game name (null when Steam/desktop is in front). */
  gameName: string | null;
  /** Capability + opt-in snapshot; null until the first RPC lands. */
  status: LearningStatus | null;
  /** Jump to the Ajustes tab (paused-state CTA). */
  onOpenSettings: () => void;
}

const TAG_KEY: Record<LearningTag, string> = {
  tdp: "learning.tag.tdp",
  fans: "learning.tag.fans",
};

/**
 * Thin persistent banner under the DeviceHeader. Makes learning VISIBLE from any
 * tab the moment the plugin opens: green "learning from {game}" with subsystem
 * chips, or a dimmed "paused" row with a CTA to re-enable telemetry. Renders
 * nothing when there's nothing to say (no game, or this device can't learn).
 */
export const LearningBanner: FC<Props> = ({ gameName, status, onOpenSettings }) => {
  const { t } = useI18n();
  const disabled = useModules();
  if (!status) return null;

  // Fold in the live module state so the banner is honest and updates the moment a
  // module is toggled: learning only runs with the learning module on, and a
  // subsystem is only being learned while its own module (Power/Fans) is enabled.
  const { state, tags } = learningBadge({
    inGame: gameName !== null,
    telemetryOn: status.telemetry_enabled && effectiveEnabled("learning", disabled),
    tdpSupported: status.tdp_supported && effectiveEnabled("power", disabled),
    fanSupported: status.fan_supported && effectiveEnabled("fans", disabled),
  });

  if (state === "hidden") return null;

  const learning = state === "learning";
  const accent = learning ? theme.color.ok : theme.color.textMuted;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: theme.space.sm,
        padding: `${theme.space.sm}px ${theme.space.md}px`,
        borderRadius: theme.radius.sm,
        background: learning ? "rgba(126,224,160,0.10)" : theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, minWidth: 0 }}>
        {learning ? (
          <LuSparkles size={14} color={accent} style={{ flexShrink: 0 }} />
        ) : (
          <LuPause size={14} color={accent} style={{ flexShrink: 0 }} />
        )}
        <span
          style={{
            fontSize: theme.font.caption,
            color: learning ? theme.color.textPrimary : theme.color.textMuted,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {learning ? t("learning.title", { name: gameName ?? "" }) : t("learning.paused")}
        </span>
      </div>

      {learning ? (
        <div style={{ display: "flex", gap: theme.space.xs, flexShrink: 0 }}>
          {tags.map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: theme.font.caption,
                padding: "1px 7px",
                borderRadius: theme.radius.sm,
                color: theme.color.ok,
                background: "rgba(126,224,160,0.14)",
                whiteSpace: "nowrap",
              }}
            >
              {t(TAG_KEY[tag])}
            </span>
          ))}
        </div>
      ) : (
        <Focusable
          onActivate={onOpenSettings}
          onClick={onOpenSettings}
          style={{
            flexShrink: 0,
            fontSize: theme.font.caption,
            color: theme.color.accent,
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          {t("learning.paused.cta")}
        </Focusable>
      )}
    </div>
  );
};
