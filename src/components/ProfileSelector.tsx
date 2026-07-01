import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";
import { LuGamepad2 } from "react-icons/lu";
import { Scope } from "../api";
import { theme } from "../theme";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

interface ProfileSelectorProps {
  scope: Scope;
  gameName: string | null;
  hasGameProfile: boolean;
  globalLabel: string;
  inheritHint: string;
  onScope: (scope: Scope) => void;
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
    ...segmentItemStyle(active),
    flex: 1,
    minWidth: 0, // lets the pill shrink so the game name can ellipsize, not bleed
    textAlign: "center",
    padding: "6px 10px",
  });

  return (
    <div>
      <Focusable style={segmentGroupStyle}>
        <Focusable style={seg(scope === "global")} onActivate={() => onScope("global")} onClick={() => onScope("global")}>
          {globalLabel}
        </Focusable>
        {gameName && (
          <Focusable style={seg(scope === "game")} onActivate={() => onScope("game")} onClick={() => onScope("game")}>
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, minWidth: 0, width: "100%" }}>
              <LuGamepad2 size={13} style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{gameName}</span>
            </span>
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
