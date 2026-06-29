import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";
import { TdpScope } from "../api";
import { theme } from "../theme";

interface ProfileSelectorProps {
  scope: TdpScope;
  gameName: string | null;
  hasGameProfile: boolean;
  globalLabel: string;
  inheritHint: string;
  onScope: (scope: TdpScope) => void;
}

export const ProfileSelector: FC<ProfileSelectorProps> = ({
  scope,
  gameName,
  hasGameProfile,
  globalLabel,
  inheritHint,
  onScope,
}) => {
  const seg = (active: boolean): CSSProperties => ({
    flex: 1,
    textAlign: "center",
    padding: "6px 10px",
    borderRadius: theme.radius.sm,
    fontSize: theme.font.body,
    fontWeight: active ? 600 : 400,
    color: active ? theme.color.textPrimary : theme.color.textMuted,
    background: active ? theme.color.accent : "transparent",
    cursor: "pointer",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    transition: "background 140ms ease, color 140ms ease",
  });

  return (
    <div>
      <Focusable
        style={{
          display: "flex",
          gap: 4,
          padding: 4,
          borderRadius: theme.radius.md,
          background: theme.color.surfaceRaised,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        }}
      >
        <Focusable style={seg(scope === "global")} onActivate={() => onScope("global")} onClick={() => onScope("global")}>
          {globalLabel}
        </Focusable>
        {gameName && (
          <Focusable style={seg(scope === "game")} onActivate={() => onScope("game")} onClick={() => onScope("game")}>
            🎮 {gameName}
          </Focusable>
        )}
      </Focusable>
      {scope === "game" && !hasGameProfile && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: "4px 2px 0" }}>
          {inheritHint}
        </div>
      )}
    </div>
  );
};
