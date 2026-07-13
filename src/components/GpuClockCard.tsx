import { FC } from "react";
import { ToggleField } from "@decky/ui";
import { LuMemoryStick } from "react-icons/lu";

import { TdpScope } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { clamp } from "../system/logic";
import { ContainedSlider } from "./ContainedSlider";
import { Collapsible } from "./Collapsible";
import { useGpuClock } from "../gpu/useGpuClock";

/** GPU clock window (min/max MHz) in Potencia. Auto by default; manual pins/limits
 *  the clock — complements the TDP for fine control. Hidden where unsupported.
 *  Per-game/global: follows the same scope tab as the rest of Potencia. */
export const GpuClockCard: FC<{ scope: TdpScope; appid: string | null }> = ({ scope, appid }) => {
  const { t } = useI18n();
  const { state, setManual, setWindow } = useGpuClock(scope, appid);

  if (!state || !state.supported || state.range_min === null || state.range_max === null) {
    return null;
  }

  const lo = state.min ?? state.range_min;
  const hi = state.max ?? state.range_max;
  const summary = state.manual ? `${lo}–${hi} MHz` : t("gpu.clock.auto");

  return (
    <div style={{ marginTop: theme.space.section }}>
    <Collapsible
      id="gpu-clock"
      icon={<LuMemoryStick size={16} />}
      title={t("gpu.clock.title")}
      summary={summary}
    >
      <ToggleField
        label={t("gpu.clock.manual")}
        description={t("gpu.clock.manual.desc")}
        checked={state.manual}
        onChange={setManual}
        bottomSeparator="none"
      />
      {state.manual && (
        <div style={{ marginTop: theme.space.sm }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("gpu.clock.min")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{lo} MHz</span>
          </div>
          <ContainedSlider
            value={lo}
            min={state.range_min}
            max={state.range_max}
            step={50}
            onChange={(v) => setWindow(Math.min(v, hi), hi)}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("gpu.clock.max")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{hi} MHz</span>
          </div>
          <ContainedSlider
            value={hi}
            min={state.range_min}
            max={state.range_max}
            step={50}
            onChange={(v) => setWindow(lo, clamp(v, lo, state.range_max ?? v))}
          />
        </div>
      )}
    </Collapsible>
    </div>
  );
};
