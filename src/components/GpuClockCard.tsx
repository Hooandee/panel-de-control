import { FC } from "react";
import { ToggleField } from "@decky/ui";
import { LuMemoryStick } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { clamp } from "../system/logic";
import { ContainedSlider } from "./ContainedSlider";
import { Collapsible } from "./Collapsible";
import { useGpuClock } from "../gpu/useGpuClock";
import { ProfileSelector } from "./ProfileSelector";
import { gpuClockPresentation, nearestLevelIndex } from "../gpu/logic";

export const GpuClockCard: FC = () => {
  const { t } = useI18n();
  const { state, scope, game, onScope, setManual, setWindow } = useGpuClock();

  if (!state || !state.supported || state.range_min === null || state.range_max === null) {
    return null;
  }

  const levels = state.levels && state.levels.length > 1 ? state.levels : null;
  const lo = state.min ?? state.range_min;
  const hi = state.max ?? state.range_max;
  const loIndex = levels ? nearestLevelIndex(levels, lo) : 0;
  const hiIndex = levels ? nearestLevelIndex(levels, hi) : 0;
  const shown = gpuClockPresentation(state);
  const summary = state.managed_by_power
    ? t("gpu.clock.auto")
    : state.manual
    ? `${shown.minimum}–${shown.maximum} MHz`
    : t("gpu.clock.auto");

  return (
    <Collapsible
      id="gpu-clock"
      icon={<LuMemoryStick size={16} />}
      title={t("gpu.clock.title")}
      summary={summary}
    >
      {game && (
        <ProfileSelector
          scope={scope}
          gameName={game.name}
          hasGameProfile={state.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("tdp.inherit")}
          onScope={onScope}
        />
      )}
      {state.managed_by_power ? (
        <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption }}>
          {t("power.managedFrequency")}
        </div>
      ) : (
        <ToggleField
          label={t("gpu.clock.manual")}
          description={t("gpu.clock.manual.desc")}
          checked={state.manual}
          onChange={setManual}
          bottomSeparator="none"
        />
      )}
      {shown.rejected && (
        <div style={{ color: theme.color.danger, fontSize: theme.font.caption }}>
          {t("gpu.clock.rejected")}
        </div>
      )}
      {state.manual && !state.managed_by_power && (
        <div style={{ marginTop: theme.space.sm }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("gpu.clock.min")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{levels ? levels[loIndex] : lo} MHz</span>
          </div>
          {levels ? (
            <ContainedSlider
              value={loIndex}
              min={0}
              max={levels.length - 1}
              step={1}
              onChange={(i) => setWindow(levels[Math.min(i, hiIndex)], levels[hiIndex])}
            />
          ) : (
            <ContainedSlider
              value={lo}
              min={state.range_min}
              max={state.range_max}
              step={50}
              onChange={(v) => setWindow(Math.min(v, hi), hi)}
            />
          )}
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("gpu.clock.max")}</span>
            <span style={{ color: theme.color.textPrimary, fontWeight: 700 }}>{levels ? levels[hiIndex] : hi} MHz</span>
          </div>
          {levels ? (
            <ContainedSlider
              value={hiIndex}
              min={0}
              max={levels.length - 1}
              step={1}
              onChange={(i) => setWindow(levels[loIndex], levels[Math.max(i, loIndex)])}
            />
          ) : (
            <ContainedSlider
              value={hi}
              min={state.range_min}
              max={state.range_max}
              step={50}
              onChange={(v) => setWindow(lo, clamp(v, lo, state.range_max ?? v))}
            />
          )}
        </div>
      )}
    </Collapsible>
  );
};
