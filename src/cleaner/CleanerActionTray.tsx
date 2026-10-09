import { FC, ReactNode, useRef } from "react";
import { useFloatingTrayClaim } from "../components/useFloatingTrayClaim";
import { stickyTrayStyle, useStickyTray } from "../components/useStickyTray";
import { theme } from "../theme";

export const CleanerActionTray: FC<{ children: ReactNode }> = ({ children }) => {
  const trayRef = useRef<HTMLDivElement>(null);
  useFloatingTrayClaim(true);
  useStickyTray(trayRef);

  return (
    <div ref={trayRef} data-cleaner-action="tray" style={{
      ...stickyTrayStyle,
      padding: theme.space.md, borderRadius: theme.radius.md,
      background: theme.color.surfaceRaised,
      boxShadow: `0 10px 32px rgba(0,0,0,0.42), inset 0 0 0 1px ${theme.color.hairline}`,
    }}>{children}</div>
  );
};
