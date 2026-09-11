import { theme } from "../theme";

export function AlertDot({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: "#ff4d4f",
        boxShadow: `0 0 0 2px ${theme.color.surface}`,
        verticalAlign: "middle",
        flexShrink: 0,
      }}
    />
  );
}
