import { FC, ReactNode, CSSProperties, useState } from "react";
import { Focusable } from "@decky/ui";
import { theme } from "../theme";

// Steam's default ring is too subtle on our custom-styled cards, so we draw an
// explicit accent ring on gamepad focus (accent token → follows the accent).
const FOCUS_RING = `inset 0 0 0 1px ${theme.color.accent}, 0 0 0 2px ${theme.color.accent}`;

/** Card-styled Focusable with a clear focus ring. `emphasized` gives a resting
 *  accent-tinted outline (the "jugando ahora" card). */
export const FocusableCard: FC<{
  onActivate: () => void;
  emphasized?: boolean;
  style?: CSSProperties;
  children: ReactNode;
}> = ({ onActivate, emphasized, style, children }) => {
  const [focused, setFocused] = useState(false);
  const resting = emphasized ? `inset 0 0 0 1px ${theme.color.accent}66` : theme.card.boxShadow;
  return (
    <Focusable
      onActivate={onActivate}
      onClick={onActivate}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      style={{
        ...theme.card,
        display: "flex",
        alignItems: "center",
        gap: theme.space.md,
        padding: `${theme.space.sm}px ${theme.space.md}px`,
        cursor: "pointer",
        transition: "box-shadow 120ms ease, transform 120ms ease",
        boxShadow: focused ? FOCUS_RING : resting,
        transform: focused ? "scale(1.01)" : "scale(1)",
        ...style,
      }}
    >
      {children}
    </Focusable>
  );
};
