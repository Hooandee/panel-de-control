import { FC, ReactNode, useLayoutEffect, useRef, useState } from "react";
import { theme } from "../theme";

interface TrayLayout {
  floating: boolean;
  left: number;
  width: number;
  bottom: number;
  height: number;
}

const INSET = 16;

function scrollViewport(anchor: HTMLElement): HTMLElement | null {
  const qam = anchor.closest<HTMLElement>("[id^='quickaccess_content_']");
  if (qam) return qam;
  const view = anchor.ownerDocument.defaultView;
  for (let node = anchor.parentElement; node; node = node.parentElement) {
    const overflow = view?.getComputedStyle(node).overflowY || node.style.overflowY;
    if (overflow === "auto" || overflow === "scroll") return node;
  }
  return null;
}

export const CleanerActionTray: FC<{ children: ReactNode }> = ({ children }) => {
  const anchorRef = useRef<HTMLDivElement>(null);
  const trayRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState<TrayLayout | null>(null);

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    const tray = trayRef.current;
    if (!anchor || !tray) return;
    const view = anchor.ownerDocument.defaultView ?? window;
    const viewport = scrollViewport(anchor);
    const update = () => {
      const rect = anchor.getBoundingClientRect();
      const bounds = viewport?.getBoundingClientRect();
      const top = Math.max(0, bounds?.top ?? 0);
      const bottom = Math.min(view.innerHeight, bounds?.bottom ?? view.innerHeight);
      const height = tray.getBoundingClientRect().height;
      const next: TrayLayout = {
        floating: rect.width > 0 && rect.right > 0 && rect.left < view.innerWidth
          && bottom > top && rect.top + height > bottom - INSET,
        left: rect.left,
        width: rect.width,
        bottom: Math.max(0, view.innerHeight - bottom) + INSET,
        height,
      };
      setLayout((current) => current && Object.keys(next).every((key) => current[key as keyof TrayLayout] === next[key as keyof TrayLayout]) ? current : next);
    };
    const resize = typeof view.ResizeObserver === "function" ? new view.ResizeObserver(update) : null;
    resize?.observe(anchor);
    resize?.observe(tray);
    if (viewport) resize?.observe(viewport);
    view.addEventListener("resize", update);
    view.addEventListener("scroll", update, true);
    // Steam moves QAM with transforms, which do not trigger resize or scroll events.
    const poll = view.setInterval(update, 100);
    update();
    return () => {
      resize?.disconnect();
      view.removeEventListener("resize", update);
      view.removeEventListener("scroll", update, true);
      view.clearInterval(poll);
    };
  }, []);

  return (
    <div ref={anchorRef} data-cleaner-action="anchor" style={{ height: layout?.height, paddingBottom: INSET, boxSizing: "content-box" }}>
      <div ref={trayRef} data-cleaner-action="tray" style={{
        position: layout?.floating ? "fixed" : "relative",
        left: layout?.floating ? layout.left : undefined,
        bottom: layout?.floating ? layout.bottom : undefined,
        width: layout?.floating ? layout.width : "100%",
        zIndex: layout?.floating ? 1000 : undefined,
        boxSizing: "border-box", padding: theme.space.md, borderRadius: theme.radius.md,
        background: theme.color.surfaceRaised,
        boxShadow: layout?.floating ? `0 10px 32px rgba(0,0,0,0.42), inset 0 0 0 1px ${theme.color.hairline}` : undefined,
      }}>{children}</div>
    </div>
  );
};
