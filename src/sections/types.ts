import { FC, ReactNode } from "react";

/**
 * A control-center section. The registry is an array of these; the navigator
 * (TabBar today, possibly a dropdown later) renders from the array and the body
 * mounts the active section's Component. Adding a section = one array entry.
 */
export interface SectionDef {
  id: string;
  icon: ReactNode;
  /** i18n key for the tab label. */
  labelKey: string;
  /** Self-contained section body; owns its own state. */
  Component: FC;
  // fullScreen?: boolean — RESERVED for a future heavy editor (e.g. fan curves).
}
