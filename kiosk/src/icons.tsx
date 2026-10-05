import { FC, ReactNode } from "react";

const Icon: FC<{ children: ReactNode }> = ({ children }) => <svg viewBox="0 0 24 24">{children}</svg>;

export const FanIcon: FC = () => (
  <Icon>
    <circle cx="12" cy="12" r="1.6" />
    <path d="M12 10.4c-.4-3 .3-6.4 3-6.9 2.4-.4 3.4 2.6 1.2 4.3-1.2.9-2.7 1.7-4.2 2.6zM13.6 12c3-.4 6.4.3 6.9 3 .4 2.4-2.6 3.4-4.3 1.2-.9-1.2-1.7-2.7-2.6-4.2zM12 13.6c.4 3-.3 6.4-3 6.9-2.4.4-3.4-2.6-1.2-4.3 1.2-.9 2.7-1.7 4.2-2.6zM10.4 12c-3 .4-6.4-.3-6.9-3-.4-2.4 2.6-3.4 4.3-1.2.9 1.2 1.7 2.7 2.6 4.2z" />
  </Icon>
);

export const ICON = {
  sun: <Icon><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>,
  speaker: <Icon><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /></Icon>,
  muted: <Icon><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M17 9l5 6M22 9l-5 6" /></Icon>,
  bolt: <Icon><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z" /></Icon>,
  camera: <Icon><rect x="3" y="6" width="18" height="13" rx="3" /><circle cx="12" cy="12.5" r="3.2" /><path d="M8.5 6l1.5-2h4l1.5 2" /></Icon>,
  keyboard: <Icon><rect x="2.5" y="6" width="19" height="12" rx="2.5" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" /></Icon>,
  dots: <Icon><circle cx="6" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="18" cy="12" r="1.3" /></Icon>,
  screenOff: <Icon><rect x="4" y="6" width="16" height="11" rx="2" /><path d="M4 4l16 16" /></Icon>,
  target: <Icon><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r=".6" /></Icon>,
  infinity: <Icon><path d="M6.5 9a3.5 3.5 0 1 0 0 6c2.5 0 3.5-6 6-6a3.5 3.5 0 1 1 0 6" /></Icon>,
  display: <Icon><rect x="3" y="5" width="18" height="12" rx="2.5" /><path d="M8 21h8M12 17v4" /></Icon>,
  power: <Icon><path d="M12 3v8" /><path d="M6.3 6.3a8 8 0 1 0 11.4 0" /></Icon>,
  auto: <Icon><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /><path d="M9.5 15l2.5-6 2.5 6M10.4 13h3.2" /></Icon>,
  leaf: <Icon><path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z" /><path d="M5 19l7-7" /></Icon>,
  gauge: <Icon><path d="M4 16a8 8 0 0 1 16 0" /><path d="M12 16l3-5" /><circle cx="12" cy="16" r="1.2" /></Icon>,
  flame: <Icon><path d="M12 3c1 3 4 5 4 9a4 4 0 0 1-8 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 0-8z" /><path d="M8.5 18.5A5 5 0 0 0 12 21a5 5 0 0 0 3.5-2.5" /></Icon>,
  rainbow: <Icon><path d="M3 17a9 9 0 0 1 18 0M6.5 17a5.5 5.5 0 0 1 11 0M10 17a2 2 0 0 1 4 0" /></Icon>,
  solid: <Icon><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" fill="currentColor" /></Icon>,
  gradient: <Icon><rect x="3" y="8" width="18" height="8" rx="4" /><path d="M9 8v8M15 8v8" /></Icon>,
  music: <Icon><path d="M5 14v4M9 9v9M13 5v13M17 11v7M21 14v4" /></Icon>,
  battery: <Icon><rect x="3" y="7" width="16" height="10" rx="2.5" /><path d="M21 11v2M6 10v4M9 10v4" /></Icon>,
  thermometer: <Icon><path d="M14 14.5V5a2 2 0 0 0-4 0v9.5a4 4 0 1 0 4 0z" /></Icon>,
  clock: <Icon><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></Icon>,
  speed: <Icon><path d="M4 12h9M4 7h13M4 17h6" /><path d="M17 15l3-3-3-3" /></Icon>,
};

export const LIGHT_MODE_ICON: Record<string, ReactNode> = {
  solid: ICON.solid,
  gradient: ICON.gradient,
  effect: ICON.rainbow,
  ambient: ICON.display,
  vu: ICON.music,
  battery: ICON.battery,
  temperature: ICON.thermometer,
  performance: ICON.gauge,
  clock: ICON.clock,
};

export const FAN_PRESET_ICON: Record<string, ReactNode> = {
  auto: ICON.auto,
  silent: ICON.leaf,
  balanced: ICON.gauge,
  performance: ICON.flame,
};
