import { FC, memo } from "react";
import { sparklinePath } from "../fans/logic";
import { theme } from "../theme";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}

/** Lightweight live line chart over a number[]. Stretches to its container width. */
const SparklineImpl: FC<SparklineProps> = ({
  values,
  width = 240,
  height = 34,
  color = theme.color.accent,
}) => {
  const d = sparklinePath(values, width, height);
  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block" }}
    >
      {d && (
        <path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
};

// Memoized: the fan poll replaces the history array each tick; memo skips the
// re-render + path recompute when this sparkline's own values are unchanged.
export const Sparkline = memo(SparklineImpl);
