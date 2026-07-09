import { CSSProperties, ComponentType, FC } from "react";
import { Focusable } from "@decky/ui";
import { LuLeaf, LuGauge, LuRocket } from "react-icons/lu";
import { TdpPresets } from "../api";
import { theme } from "../theme";

interface PresetsProps {
  presets: TdpPresets;
  onAc: boolean;
  // Current fixed target watts; the matching preset shows active until it changes.
  activeWatts: number;
  labels: { save: string; balanced: string; turbo: string };
  onPick: (watts: number) => void;
}

export const Presets: FC<PresetsProps> = ({ presets, onAc, activeWatts, labels, onPick }) => {
  const turbo = onAc ? presets.turbo_ac : presets.turbo;
  const items: { Icon: ComponentType<{ size?: number }>; label: string; watts: number }[] = [
    { Icon: LuLeaf, label: labels.save, watts: presets.quiet },
    { Icon: LuGauge, label: labels.balanced, watts: presets.balanced },
    { Icon: LuRocket, label: labels.turbo, watts: turbo },
  ];
  const btn = (active: boolean): CSSProperties => ({
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 2,
    padding: "6px 4px",
    borderRadius: theme.radius.sm,
    background: active ? "rgba(78,161,255,0.18)" : theme.color.surfaceRaised,
    boxShadow: `inset 0 0 0 ${active ? 1.5 : 1}px ${active ? theme.color.accent : theme.color.hairline}`,
    color: active ? theme.color.accent : theme.color.textPrimary,
    fontSize: theme.font.caption,
    cursor: "pointer",
  });

  return (
    <Focusable style={{ display: "flex", gap: 6, marginTop: 8 }}>
      {items.map((it) => {
        const active = Math.round(activeWatts) === Math.round(it.watts);
        return (
          <Focusable key={it.label} style={btn(active)} onActivate={() => onPick(it.watts)} onClick={() => onPick(it.watts)}>
            <it.Icon size={16} />
            <span>{it.label}</span>
            <span style={{ color: active ? theme.color.accent : theme.color.textMuted }}>{it.watts}W</span>
          </Focusable>
        );
      })}
    </Focusable>
  );
};
