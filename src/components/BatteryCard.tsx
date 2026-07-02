import { FC } from "react";
import { ToggleField } from "@decky/ui";
import { LuBatteryFull, LuBatteryLow, LuHeartPulse, LuPlug, LuRefreshCw, LuZap } from "react-icons/lu";

import { BatteryState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { batteryColor, batteryStatusKey, clampThreshold, formatCapacity, formatEta } from "../system/battery";
import { ContainedSlider } from "./ContainedSlider";

interface Props {
  state: BatteryState;
  onSetLimit: (enabled: boolean, percent: number) => void;
}

/** Horizontal battery glyph that fills with the charge %, colored by state, with
 *  an optional threshold marker when a charge limit is active. */
const BatteryGlyph: FC<{ percent: number; charging: boolean; limit: number | null }> = ({
  percent,
  charging,
  limit,
}) => {
  const W = 96;
  const H = 40;
  const R = 6;
  const pad = 4;
  const inner = W - pad * 2;
  const fill = (Math.max(0, Math.min(100, percent)) / 100) * inner;
  const color = batteryColor(percent, charging);
  const limitX = limit !== null ? pad + (limit / 100) * inner : null;
  return (
    <svg width={W + 8} height={H} viewBox={`0 0 ${W + 8} ${H}`} style={{ flexShrink: 0 }}>
      {/* shell */}
      <rect x={1} y={1} width={W - 2} height={H - 2} rx={R} ry={R}
        fill="none" stroke={theme.color.hairline} strokeWidth={2} />
      {/* terminal nub */}
      <rect x={W} y={H / 2 - 7} width={6} height={14} rx={2} fill={theme.color.hairline} />
      {/* fill */}
      <rect x={pad} y={pad} width={fill} height={H - pad * 2} rx={R - 2} ry={R - 2} fill={color} />
      {/* charge-limit marker */}
      {limitX !== null && (
        <line x1={limitX} y1={2} x2={limitX} y2={H - 2}
          stroke={theme.color.textPrimary} strokeWidth={2} strokeDasharray="3 2" />
      )}
    </svg>
  );
};

const Chip: FC<{ icon: React.ReactNode; label: string; value: string; grow?: number }> = ({ icon, label, value, grow = 1 }) => (
  <div style={{ ...theme.tile, flex: `${grow} 1 0`, display: "flex", flexDirection: "column", gap: 2 }}>
    <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
      {icon} {label}
    </span>
    <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
      {value}
    </span>
  </div>
);

export const BatteryCard: FC<Props> = ({ state, onSetLimit }) => {
  const { t } = useI18n();
  const { battery: b, charge_limit: cl } = state;

  if (!b.present) {
    return (
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("system.battery.absent")}
      </div>
    );
  }

  const percent = b.percent ?? 0;
  const charging = b.status === "Charging";
  const statusKey = batteryStatusKey(b.status, b.ac_online);

  // Status line: charging / discharging (+eta) / connected.
  let statusText: string;
  let statusIcon: React.ReactNode;
  if (statusKey === "charging") {
    statusText = t("system.battery.charging");
    statusIcon = <LuZap size={13} color={theme.color.accent} />;
  } else if (statusKey === "connected") {
    statusText = t("system.battery.connected");
    statusIcon = <LuPlug size={13} color={theme.color.textMuted} />;
  } else {
    const eta = formatEta(b.eta_seconds);
    statusText = eta === "—" ? t("system.battery.discharging") : `${t("system.battery.discharging")} · ${eta}`;
    const Icon = percent <= 15 ? LuBatteryLow : LuBatteryFull;
    statusIcon = <Icon size={13} color={theme.color.textMuted} />;
  }

  return (
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
        {/* Hero: glyph + big %, then the status on its own full-width row so a
            long "Discharging · 2h 33m" never wraps mid-phrase. */}
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
          <BatteryGlyph percent={percent} charging={charging} limit={cl.supported && cl.enabled && cl.adjustable ? cl.percent : null} />
          <span style={{ fontSize: theme.font.value, fontWeight: 700, lineHeight: 1, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
            {b.percent === null ? "—" : `${percent}%`}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted, whiteSpace: "nowrap" }}>
          {statusIcon} {statusText}
        </div>

        {/* Health bar */}
        {b.health_percent !== null && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
                <LuHeartPulse size={12} /> {t("system.battery.health")}
              </span>
              <span style={{ color: theme.color.textPrimary, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{b.health_percent}%</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: theme.color.hairline, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${b.health_percent}%`, background: theme.color.ok }} />
            </div>
          </div>
        )}

        {/* Stat chips */}
        {(b.cycle_count !== null || b.energy_full_mwh !== null) && (
          <div style={{ display: "flex", gap: theme.space.sm }}>
            {b.cycle_count !== null && (
              <Chip icon={<LuRefreshCw size={11} />} label={t("system.battery.cycles")} value={String(b.cycle_count)} grow={1} />
            )}
            {b.energy_full_mwh !== null && (
              <Chip
                icon={<LuBatteryFull size={11} />}
                label={t("system.battery.capacity")}
                grow={2}
                value={formatCapacity(b.energy_full_mwh, b.energy_full_design_mwh)}
              />
            )}
          </div>
        )}

        {/* Charge limit — hidden entirely on devices that can't cap charge
            (never show a dead/disabled control). */}
        {cl.supported && (
          <div style={{ borderTop: `1px solid ${theme.color.hairline}`, paddingTop: theme.space.xs }}>
            <ToggleField
              label={t("system.battery.limit")}
              description={t("system.battery.limit.desc")}
              checked={cl.enabled}
              onChange={(v) => onSetLimit(v, cl.percent)}
            />
            {cl.enabled && cl.adjustable && (
              <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <ContainedSlider
                    value={cl.percent}
                    min={cl.min}
                    max={cl.max}
                    step={5}
                    showValue={false}
                    onChange={(v) => onSetLimit(true, clampThreshold(v, cl.min, cl.max))}
                  />
                </div>
                <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums", minWidth: 40, textAlign: "right" }}>
                  {cl.percent}%
                </span>
              </div>
            )}
            {cl.enabled && !cl.adjustable && (
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {t("system.battery.limit.fixed", { percent: cl.percent })}
              </div>
            )}
          </div>
        )}
      </div>
  );
};
