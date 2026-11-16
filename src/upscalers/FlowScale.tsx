import { useEffect, useRef, useState, type FC } from "react";
import { ContainedSlider } from "../components/ContainedSlider";
import { useI18n } from "../i18n";

// lsfg-vk rejects a flow_scale outside 0.25-1.0.
export const FLOW_SCALE_MIN = 25;
export const FLOW_SCALE_MAX = 100;
const FLOW_SCALE_STEP = 5;
const COMMIT_DELAY_MS = 350;
// Steam lays notches out at a fixed width each, so more than a few overflow the track. Only the two ends are
// labelled: a third label touches its neighbours in Spanish, German and French.
const NOTCH_COUNT = 2;

export type FlowPreset = "quality" | "balanced" | "performance" | "fastest";
export type FlowMode = FlowPreset | "manual";
export const FLOW_PRESETS: Record<FlowPreset, number> = { quality: 1, balanced: 0.75, performance: 0.5, fastest: 0.25 };
export const FLOW_MODES: FlowMode[] = ["quality", "balanced", "performance", "fastest", "manual"];

/** A preset value shows as that preset; anything else, or an explicit manual choice, shows as Manual. */
export const flowMode = (profile: { flow_scale: number; flow_manual?: boolean }): FlowMode => {
  if (profile.flow_manual) return "manual";
  const preset = (Object.keys(FLOW_PRESETS) as FlowPreset[]).find((key) => FLOW_PRESETS[key] === profile.flow_scale);
  return preset ?? "manual";
};

export const clampFlowScale = (percent: number) =>
  Math.max(FLOW_SCALE_MIN, Math.min(FLOW_SCALE_MAX, Math.round(percent / FLOW_SCALE_STEP) * FLOW_SCALE_STEP));

/** Flow scale in percent. The value is saved once the slider rests, not on every step of the drag. */
export const FlowScale: FC<{ appid: string; value: number; disabled: boolean; onCommit: (flowScale: number) => void }> = ({ appid, value, disabled, onCommit }) => {
  const { t } = useI18n();
  const [percent, setPercent] = useState(() => clampFlowScale(value * 100));
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = () => { if (pending.current !== null) clearTimeout(pending.current); pending.current = null; };
  useEffect(() => { setPercent(clampFlowScale(value * 100)); return cancel; }, [appid, value]);
  useEffect(() => { if (disabled) cancel(); }, [disabled]);
  const slide = (next: number) => {
    if (disabled) return;
    const clamped = clampFlowScale(next);
    setPercent(clamped);
    cancel();
    pending.current = setTimeout(() => { pending.current = null; onCommit(clamped / 100); }, COMMIT_DELAY_MS);
  };
  const notchLabels = [
    { notchIndex: 0, label: t("up.lsfg.flowScale.performance") },
    { notchIndex: 1, label: t("up.lsfg.flowScale.quality") },
  ];
  return <ContainedSlider label={t("up.lsfg.flowScale")} value={percent} min={FLOW_SCALE_MIN} max={FLOW_SCALE_MAX} step={FLOW_SCALE_STEP}
    notchCount={NOTCH_COUNT} notchLabels={notchLabels} notchTicksVisible={false} disabled={disabled} bottomSeparator="none" onChange={slide} />;
};
