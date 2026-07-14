import { ComponentType, FC } from "react";
import { Focusable } from "@decky/ui";
import { LuLeaf, LuGauge, LuRocket } from "react-icons/lu";
import { iconChipStyle } from "./chipStyle";

interface FirmwareModesProps {
  // Choices from the firmware (e.g. ["low-power","balanced","performance","custom"]).
  modes: string[];
  active: string; // current firmware_mode ("custom" = none of the chips active)
  labels: Record<string, string>;
  onPick: (mode: string) => void;
}

const ICONS: Record<string, ComponentType<{ size?: number }>> = {
  "low-power": LuLeaf,
  balanced: LuGauge,
  performance: LuRocket,
};

export const FirmwareModes: FC<FirmwareModesProps> = ({ modes, active, labels, onPick }) => {
  // "custom" is represented by moving the slider, not a chip.
  const items = modes.filter((m) => m !== "custom");
  return (
    <Focusable style={{ display: "flex", gap: 6, marginTop: 8 }}>
      {items.map((m) => {
        const Icon = ICONS[m] ?? LuGauge;
        return (
          <Focusable key={m} style={iconChipStyle(active === m)} onActivate={() => onPick(m)} onClick={() => onPick(m)}>
            <Icon size={16} />
            <span>{labels[m] ?? m}</span>
          </Focusable>
        );
      })}
    </Focusable>
  );
};
