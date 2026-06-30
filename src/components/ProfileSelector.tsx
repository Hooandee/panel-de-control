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
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><LuGamepad2 size={13} /> {gameName}</span>
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
