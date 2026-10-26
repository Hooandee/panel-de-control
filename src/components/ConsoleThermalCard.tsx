import { FC, useEffect, useRef, useState } from "react";
import { ToggleField } from "@decky/ui";
import { LuShieldAlert } from "react-icons/lu";

import { ConsoleState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Collapsible } from "./Collapsible";
import { ContainedSlider } from "./ContainedSlider";

const THRESHOLD_MIN = 80;
const THRESHOLD_MAX = 100;
const SLIDER_SETTLE_MS = 400;

export const ConsoleThermalCard: FC<{
  state: ConsoleState;
  onChange: (enabled: boolean | null, threshold: number | null, alarm: boolean | null) => void;
}> = ({ state, onChange }) => {
  const { t } = useI18n();
  const guard = state.guard!;
  const [threshold, setThreshold] = useState(guard.threshold);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<number | null>(null);
  const send = useRef(onChange);
  send.current = onChange;
  useEffect(() => setThreshold(guard.threshold), [guard.threshold]);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    if (pending.current !== null) send.current(null, pending.current, null);
  }, []);

  const onSlide = (value: number) => {
    setThreshold(value);
    pending.current = value;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      pending.current = null;
      onChange(null, value, null);
    }, SLIDER_SETTLE_MS);
  };

  const working = guard.fan_supported && guard.blocked === null;
  const summary = guard.active ? t("console.guard.activeShort")
    : guard.enabled && working ? t("console.guard.at", { c: guard.effective_threshold })
      : guard.enabled ? t("console.guard.pausedShort") : t("system.off");
  return (
    <Collapsible id="console-guard" icon={<LuShieldAlert size={16} />} title={t("console.guard.title")} summary={summary}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        {guard.active && (
          <span style={{ fontSize: theme.font.caption, color: theme.color.warn, lineHeight: 1.4 }}>
            {t(guard.fan_held ? "console.guard.active" : "console.guard.retrying")}
          </span>
        )}
        {guard.enabled && guard.blocked === "fan_module_off" && (
          <span style={{ fontSize: theme.font.caption, color: theme.color.warn, lineHeight: 1.4 }}>{t("console.guard.fanModuleOff")}</span>
        )}
        {guard.enabled && guard.effective_threshold > threshold && (
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
            {t("console.guard.aboveTarget", { c: guard.effective_threshold })}
          </span>
        )}
        {guard.fan_supported && (
          <ToggleField
            label={t("console.guard.toggle")}
            description={t("console.guard.desc")}
            checked={guard.enabled}
            onChange={(next: boolean) => onChange(next, null, null)}
            bottomSeparator="none"
          />
        )}
        {(guard.enabled || guard.alarm) && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <span>{t("console.guard.threshold")}</span>
              <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{threshold} °C</span>
            </div>
            <ContainedSlider value={threshold} min={THRESHOLD_MIN} max={THRESHOLD_MAX} step={1} onChange={onSlide} />
          </>
        )}
        {guard.alarm_supported && (
          <ToggleField
            label={t("console.guard.alarm")}
            description={t("console.guard.alarm.desc")}
            checked={guard.alarm}
            onChange={(next: boolean) => onChange(null, null, next)}
            bottomSeparator="none"
          />
        )}
      </div>
    </Collapsible>
  );
};
