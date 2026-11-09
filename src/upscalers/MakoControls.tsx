import { useEffect, useRef, useState, type FC } from "react";
import { ContainedSlider } from "../components/ContainedSlider";
import type { MakoProfile } from "../api";
import { useI18n } from "../i18n";
import { ListCard, ListRow, PickerButton } from "./parts";

const MULTIPLIERS = [2, 3, 4, 5] as const;
const FLOWS = ["quality", "balanced", "performance", "fastest"] as const;

export const MakoControls: FC<{
  profile: MakoProfile;
  disabled: boolean;
  duo: boolean;
  appid: string;
  onChange: (config: MakoProfile) => void;
}> = ({ profile, disabled, duo, appid, onChange }) => {
  const { t } = useI18n();
  const [target, setTarget] = useState(profile.target_fps);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = () => { if (pending.current !== null) clearTimeout(pending.current); pending.current = null; };
  useEffect(() => { setTarget(profile.target_fps); return cancel; }, [appid, profile]);
  useEffect(() => { if (disabled) cancel(); }, [disabled]);
  const change = (next: MakoProfile) => { cancel(); onChange({ ...next, target_fps: target }); };
  const slide = (value: number) => {
    if (disabled) return;
    const next = Math.max(30, Math.min(240, Math.round(value)));
    setTarget(next);
    cancel();
    pending.current = setTimeout(() => { pending.current = null; onChange({ ...profile, target_fps: next }); }, 350);
  };
  return <ListCard>
    <PickerButton duo={duo} controlId={`${appid}:mako-mode`} showLabel label={t("up.mako.mode")}
      value={profile.mode} disabled={disabled}
      options={(["fixed", "adaptive"] as const).map(mode => ({ value: mode, label: t(`up.mako.${mode}`) }))}
      onChange={mode => change({ ...profile, mode })} />
    {profile.mode === "fixed" ? <PickerButton duo={duo} controlId={`${appid}:mako-multiplier`} showLabel label={t("up.lsfg.multiplier")}
      value={String(profile.multiplier)} disabled={disabled}
      options={MULTIPLIERS.map(multiplier => ({ value: String(multiplier), label: `×${multiplier}` }))}
      onChange={value => change({ ...profile, multiplier: Number(value) as MakoProfile["multiplier"] })} /> : <>
      <ContainedSlider label={t("up.mako.target")} value={target} min={30} max={240} step={1}
        showValue disabled={disabled} bottomSeparator="none" onChange={slide} />
      <PickerButton duo={duo} controlId={`${appid}:mako-max`} showLabel label={t("up.mako.max")}
        value={String(profile.max_multiplier)} disabled={disabled}
        options={MULTIPLIERS.map(multiplier => ({ value: String(multiplier), label: `×${multiplier}` }))}
        onChange={value => change({ ...profile, max_multiplier: Number(value) as MakoProfile["max_multiplier"] })} />
    </>}
    <PickerButton duo={duo} controlId={`${appid}:mako-flow`} showLabel label={t("up.lsfg.flow")}
      value={profile.flow} disabled={disabled}
      options={FLOWS.map(flow => ({ value: flow, label: t(`up.lsfg.flow.${flow}`) }))}
      onChange={flow => change({ ...profile, flow })} />
    <ListRow label={t("up.lsfg.light")} caption={t("up.lsfg.lightHint")} on={profile.performance} disabled={disabled}
      onPress={() => change({ ...profile, performance: !profile.performance })} />
  </ListCard>;
};
