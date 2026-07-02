// Small red alert dot to render next to a tab label when an update is available.
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
        marginLeft: 6,
        verticalAlign: "middle",
        flexShrink: 0,
      }}
    />
  );
}
