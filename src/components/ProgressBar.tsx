import { FC } from "react";
import { clamp } from "../system/logic";
import { theme } from "../theme";

/** Thin learning-progress bar (green fill over a faint track). value ∈ [0,1]. */
export const ProgressBar: FC<{ value: number }> = ({ value }) => (
  <div style={{ height: 6, borderRadius: 4, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
    <div style={{ width: `${Math.round(clamp(value, 0, 1) * 100)}%`, height: "100%", background: theme.color.ok, borderRadius: 4 }} />
  </div>
);
