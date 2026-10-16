import { FC } from "react";
import { Focusable } from "@decky/ui";
import { LuCpu, LuLink2, LuMemoryStick, LuUnlink2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

export type PowerTarget = "cpu" | "gpu";

interface PowerTargetTabsProps {
  target: PowerTarget;
  cpuLevel: number;
  gpuLevel: number;
  linked: boolean;
  onTarget: (target: PowerTarget) => void;
  onLinked: (linked: boolean) => void;
}

const HEIGHT = 32;

export const PowerTargetTabs: FC<PowerTargetTabsProps> = ({
  target,
  cpuLevel,
  gpuLevel,
  linked,
  onTarget,
  onLinked,
}) => {
  const { t } = useI18n();
  const tab = (value: PowerTarget, Icon: typeof LuCpu, label: string, level: number) => {
    const active = value === target;
    return (
      <Focusable
        key={value}
        role="tab"
        aria-selected={active}
        onActivate={() => onTarget(value)}
        onClick={() => onTarget(value)}
        style={{
          flex: "1 1 0",
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 5,
          borderRadius: 999,
          fontSize: theme.font.caption,
          fontWeight: 700,
          letterSpacing: "0.06em",
          cursor: "pointer",
          color: active ? theme.color.accent : theme.color.textMuted,
          background: active ? `rgba(${theme.color.accentRgb},0.16)` : "transparent",
          boxShadow: active ? `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.55)` : "none",
          transition: "background 140ms ease, color 140ms ease",
        }}
      >
        <Icon size={13} />
        <span>{label}</span>
        <span style={{ fontWeight: 600, opacity: 0.75, fontVariantNumeric: "tabular-nums" }}>{level}</span>
      </Focusable>
    );
  };

  return (
    <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.sm, alignItems: "stretch" }}>
      <Focusable
        role="tablist"
        aria-label={t("tdp.target.label")}
        flow-children="row"
        style={{
          flex: 1,
          display: "flex",
          height: HEIGHT,
          padding: 3,
          borderRadius: 999,
          background: theme.color.surfaceRaised,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        }}
      >
        {tab("cpu", LuCpu, t("tdp.target.cpu"), cpuLevel)}
        {tab("gpu", LuMemoryStick, t("tdp.target.gpu"), gpuLevel)}
      </Focusable>
      <Focusable
        role="switch"
        aria-checked={linked}
        aria-label={linked ? t("tdp.target.unlink") : t("tdp.target.link")}
        onActivate={() => onLinked(!linked)}
        onClick={() => onLinked(!linked)}
        style={{
          width: HEIGHT + 6,
          height: HEIGHT,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 999,
          cursor: "pointer",
          background: theme.color.surfaceRaised,
          color: linked ? theme.color.accent : theme.color.textMuted,
          boxShadow: `inset 0 0 0 1px ${linked ? `rgba(${theme.color.accentRgb},0.6)` : theme.color.hairline}`,
        }}
      >
        {linked ? <LuLink2 size={15} /> : <LuUnlink2 size={15} />}
      </Focusable>
    </Focusable>
  );
};
