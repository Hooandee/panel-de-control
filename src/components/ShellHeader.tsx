import { type ReactNode } from "react";
import { theme } from "../theme";
import { CompactBackAction } from "./CompactBackAction";

export interface ShellHeaderProps {
  onBack: () => void;
  trailing?: ReactNode;
}

export function ShellHeader({ onBack, trailing }: ShellHeaderProps) {
  return (
    <div
      data-testid="detail-back-row"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: theme.space.sm,
        minHeight: 28,
      }}
    >
      <CompactBackAction onBack={onBack} />
      {trailing ? (
        <div style={{ minWidth: 0, flex: "1 1 auto", display: "flex", justifyContent: "flex-end" }}>
          {trailing}
        </div>
      ) : null}
    </div>
  );
}
