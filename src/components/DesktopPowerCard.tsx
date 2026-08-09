import { CSSProperties, FC, ReactNode, useEffect, useRef, useState } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuGauge, LuRefreshCw, LuScale, LuVolumeX, LuZap } from "react-icons/lu";

import { DesktopPowerMode } from "../api";
import { clockText, metricText, vramView } from "../desktop/presentation";
import { useDesktopState } from "../desktop/useDesktop";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { DesktopPowerDial } from "./DesktopPowerDial";
import { DesktopPowerSlider } from "./DesktopPowerSlider";
import { segmentItemStyle } from "./segmented";

const MODES: DesktopPowerMode[] = ["free", "silent", "balanced", "performance"];
const ICONS: Record<Exclude<DesktopPowerMode, "custom">, ReactNode> = {
  free: <LuRefreshCw size={13} />,
  silent: <LuVolumeX size={13} />,
  balanced: <LuScale size={13} />,
  performance: <LuZap size={13} />,
};

const metricGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.space.sm,
};

const Metric: FC<{ label: string; value: string; wide?: boolean; progress?: number; testId?: string }> = ({ label, value, wide, progress, testId }) => (
  <div
    data-testid={testId}
    style={{
      ...theme.tile,
      gridColumn: wide ? "1 / -1" : undefined,
      boxSizing: "border-box",
      display: "flex",
      flexDirection: "column",
      justifyContent: progress == null ? "flex-start" : "space-between",
      gap: progress == null ? 2 : theme.space.xs,
      minHeight: wide ? 58 : 66,
    }}
  >
    <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: theme.color.textMuted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
    <span style={{ fontSize: value.length > 14 ? 13 : 20, fontWeight: 680, lineHeight: 1.05, letterSpacing: value.length > 14 ? 0 : "-0.035em", color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</span>
    {progress != null && (
      <div style={{ height: 4, overflow: "hidden", borderRadius: 4, background: theme.color.hairline }}>
        <div style={{ width: `${progress * 100}%`, height: "100%", borderRadius: 4, background: "#43d8ff" }} />
      </div>
    )}
  </div>
);

export const DesktopPowerCard: FC = () => {
  const { t } = useI18n();
  const control = useDesktopState(true);
  const state = control.state;
  const power = state?.power;
  const [cpu, setCpu] = useState(23);
  const [gpu, setGpu] = useState(80);
  const commit = useRef<number | null>(null);

  useEffect(() => {
    if (power?.cpu_w != null) setCpu(power.cpu_w);
    if (power?.gpu_w != null) setGpu(power.gpu_w);
  }, [power?.cpu_w, power?.gpu_w]);
  useEffect(() => () => { if (commit.current != null) window.clearTimeout(commit.current); }, []);

  if (!state?.enabled) return null;

  const queue = (nextCpu: number, nextGpu: number) => {
    if (commit.current != null) window.clearTimeout(commit.current);
    commit.current = window.setTimeout(() => control.applyLimits(nextCpu, nextGpu), 250);
  };
  const telemetry = state.telemetry;
  const gpuRange = power?.gpu_min_w != null && power.gpu_max_w != null;
  const unavailable = t("desktop.metric.unavailable");
  const vram = vramView(telemetry?.vram_used_mb ?? null, telemetry?.vram_total_mb ?? null, unavailable);
  const policy = power?.cpu_policy_supported && power.cpu_policy
    ? t(`desktop.cpu.policy.${power.cpu_policy}`)
    : null;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
          <LuGauge size={18} color={theme.color.accent} />
          <span style={{ fontSize: theme.font.body, fontWeight: 650, color: theme.color.textPrimary }}>{t("desktop.power.title")}</span>
        </div>

        <Focusable style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6 }}>
          {MODES.map((mode) => {
            const active = power?.mode === mode;
            const label = t(`desktop.mode.${mode}`);
            return (
              <Focusable key={mode}
                style={{ ...segmentItemStyle(active), boxSizing: "border-box", minWidth: 0, minHeight: "0px", height: 32, padding: "4px 5px", color: active ? theme.color.onAccent : theme.color.textMuted, boxShadow: `inset 0 0 0 1px ${active ? "transparent" : theme.color.hairline}` }}
                title={label} aria-label={label}
                onActivate={() => control.applyMode(mode)} onClick={() => control.applyMode(mode)}>
                {ICONS[mode as Exclude<DesktopPowerMode, "custom">]}
                <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
              </Focusable>
            );
          })}
        </Focusable>

        <div data-testid="desktop-power-hero" style={{ display: "grid", gridTemplateColumns: "124px minmax(0, 1fr)", alignItems: "center", gap: theme.space.md, padding: theme.space.sm, borderRadius: theme.radius.md, background: `radial-gradient(100% 100% at 0% 50%, rgba(${theme.color.accentRgb},0.08), transparent 62%), rgba(255,255,255,0.025)`, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
          <DesktopPowerDial value={power?.gpu_supported ? gpu : (power?.gpu_w ?? null)} min={power?.gpu_min_w ?? null} max={power?.gpu_max_w ?? null}
            label={t("desktop.gpu.limit")} unavailable={unavailable} />
          <div style={{ minWidth: 0, display: "flex", flexDirection: "column", alignItems: "flex-start", gap: theme.space.xs }}>
            <span style={{ fontSize: 17, fontWeight: 650, lineHeight: 1.15, color: theme.color.textPrimary }}>{t("desktop.power.available")}</span>
            {gpuRange && <span style={{ fontSize: 10, lineHeight: 1.35, color: theme.color.textMuted }}>{t("desktop.power.range", { min: power!.gpu_min_w!, max: power!.gpu_max_w! })}</span>}
          </div>
        </div>

        {power?.gpu_supported && gpuRange && (
          <DesktopPowerSlider
            label={t("desktop.gpu.limit")}
            value={gpu}
            min={power.gpu_min_w!}
            max={power.gpu_max_w!}
            onChange={(value) => { setGpu(value); queue(cpu, value); }}
          />
        )}
        {power?.cpu_supported && (
          <DesktopPowerSlider
            label={t("desktop.cpu.limit")}
            value={cpu}
            min={power.cpu_min_w}
            max={power.cpu_max_w}
            onChange={(value) => { setCpu(value); queue(value, gpu); }}
          />
        )}
        {policy && (
          <span data-testid="desktop-cpu-policy" style={{ minWidth: 0, padding: "0 4px", color: theme.color.textMuted, fontSize: 10, fontWeight: 600, lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            CPU · {policy}
          </span>
        )}

        <Focusable
          data-testid="desktop-power-metrics"
          role="group"
          aria-label={t("desktop.power.metrics")}
          onActivate={() => {}}
          noFocusRing
          style={metricGrid}
        >
          <Metric testId="desktop-metric-gpu-draw" label={t("desktop.gpu.draw")}
            value={metricText(telemetry?.gpu_watts ?? null, "W", unavailable)} />
          <Metric label={t("desktop.gpu.clock")}
            value={clockText(telemetry?.gpu_clock_mhz ?? null, t("desktop.metric.idle"), unavailable)} />
          <Metric wide label={t("desktop.vram")}
            value={vram.total ? `${vram.value} / ${vram.total}` : vram.value} progress={vram.fraction} />
        </Focusable>

        <span style={{ fontSize: 10, lineHeight: 1.35, color: theme.color.textMuted }}>{t("desktop.power.free.note")}</span>
      </div>
    </PanelSectionRow>
  );
};
