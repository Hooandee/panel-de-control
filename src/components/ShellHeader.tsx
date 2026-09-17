import { type ReactNode } from "react";
import { theme } from "../theme";
import { CompactBackAction } from "./CompactBackAction";

export interface ShellHeaderProps {
  onBack: () => void;
  backLabel?: string;
  trailing?: ReactNode;
  testId?: string;
}

export function ShellHeader({
  onBack,
  backLabel,
  trailing,
  testId = "detail-back-row",
}: ShellHeaderProps) {
  return (
    <div
      data-testid={testId}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: theme.space.sm,
        minHeight: 28,
      }}
    >
      <CompactBackAction onBack={onBack} label={backLabel} />
      {trailing ? (
        <div style={{ minWidth: 0, flex: "1 1 auto", display: "flex", justifyContent: "flex-end" }}>
          {trailing}
        </div>
      ) : null}
    </div>
  );
}
