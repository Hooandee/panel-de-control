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
  gameName: string | null;
  status: LearningStatus | null;
  onOpenSettings: () => void;
  scope: readonly LearningTag[];
}

const TAG_KEY: Record<LearningTag, string> = {
  tdp: "learning.tag.tdp",
  fans: "learning.tag.fans",
};

export const LearningBanner: FC<Props> = ({ gameName, status, onOpenSettings, scope }) => {
  const { t } = useI18n();
  const disabledModules = useModules();
  if (!status) return null;

  const { state, tags } = learningBadge({
    inGame: gameName !== null,
    telemetryOn: status.telemetry_enabled && effectiveEnabled("learning", disabledModules),
    tdpSupported: status.tdp_supported && effectiveEnabled("power", disabledModules),
    fanSupported: status.fan_supported && effectiveEnabled("fans", disabledModules),
    scope,
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
