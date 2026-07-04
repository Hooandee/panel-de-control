import { FC } from "react";
import { Spinner } from "@decky/ui";

import { theme } from "../theme";

/**
 * Compact, centered loading indicator — the elegant stand-in for Decky's
 * full-size <Spinner/> (which fills the whole panel). Used for the startup and
 * per-section load states so a brief fetch shows a small, tidy spinner instead
 * of a giant one.
 */
export const Loading: FC = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: `${theme.space.lg}px 0` }}>
    <Spinner style={{ width: 24, height: 24 }} />
  </div>
);
