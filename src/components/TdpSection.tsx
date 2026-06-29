import { Focusable, PanelSectionRow, SliderField, Spinner, ToggleField } from "@decky/ui";
import { CSSProperties, FC } from "react";

import { TdpState, TdpScope, PowerDraw } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { fraction, zoneFor } from "../tdp/logic";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";
import { AdvancedBoost } from "./AdvancedBoost";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

// null = "Off" (no FPS target; auto-TDP runs in its plain load-tracking mode).
const FPS_OPTIONS: (number | null)[] = [null, 30, 40, 45, 50, 60];

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  power: PowerDraw | null;
  onScope: (scope: TdpScope) => void;
  onWatts: (watts: number) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onResetAuto: () => void;
  onAutoTdp: (enabled: boolean) => void;
  onFpsTarget: (target: number | null) => void;
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, power, onScope, onWatts, onSetLevels, onResetAuto, onAutoTdp, onFpsTarget }) => {
  const { t } = useI18n();

  if (!tdp) return <Spinner />;

  if (!tdp.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  }

  const view =
    scope === "global"
      ? { watts: tdp.global_watts, levels: tdp.global_levels, auto: tdp.global_auto }
      : { watts: tdp.watts, levels: tdp.levels, auto: tdp.auto };
  // Active ceiling: on battery the device-aware cap (max), on charger max_ac.
  // Never offer more than the current power source can deliver.
  const activeMax = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  const zone = zoneFor(fraction(view.watts, tdp.limits.min, activeMax));
  const isAutoOn = power?.auto_tdp ?? false;
  const atCeiling = Math.min(view.watts, activeMax) >= activeMax;
  // Honest "can't reach the target": we're pinned at the active ceiling and the
  // real fps is still meaningfully below the target. Never claim a hit target.
  const belowTarget =
    isAutoOn &&
    power?.target_fps != null &&
    power?.fps != null &&
    power.fps < power.target_fps - 3 &&
    (power.setpoint ?? 0) >= activeMax;

  const fpsItem = (active: boolean): CSSProperties => ({
    ...segmentItemStyle(active),
    flex: 1,
    textAlign: "center",
    padding: "5px 4px",
  });

  return (
    <>
      <PanelSectionRow>
        <ProfileSelector
          scope={scope}
          gameName={game?.name ?? null}
          hasGameProfile={tdp.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("tdp.inherit")}
          onScope={onScope}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <PowerArc
          watts={view.watts}
          limits={tdp.limits}
          onAc={tdp.on_ac}
          zoneLabel={t(`tdp.zone.${zone.key}`)}
          actualWatts={power?.watts ?? null}
          gpuBusy={power?.gpu_busy ?? null}
          auto={isAutoOn}
          setpoint={power?.setpoint ?? null}
          fps={power?.fps ?? null}
          targetFps={power?.target_fps ?? null}
          atMaxBelowTarget={belowTarget}
        />
      </PanelSectionRow>
      {isAutoOn && (
        <PanelSectionRow>
          <div>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: "0 2px 4px" }}>
              {t("tdp.fps.title")}
            </div>
            <Focusable style={segmentGroupStyle}>
              {FPS_OPTIONS.map((opt) => {
                const active = (power?.target_fps ?? null) === opt;
                return (
                  <Focusable
                    key={opt ?? "off"}
                    style={fpsItem(active)}
                    onActivate={() => onFpsTarget(opt)}
                    onClick={() => onFpsTarget(opt)}
                  >
                    {opt === null ? t("tdp.fps.off") : opt}
                  </Focusable>
                );
              })}
            </Focusable>
          </div>
        </PanelSectionRow>
      )}
      {!isAutoOn && (
        <>
          <PanelSectionRow>
            <SliderField
              value={Math.min(view.watts, activeMax)}
              min={tdp.limits.min}
              max={activeMax}
              step={1}
              showValue
              onChange={onWatts}
            />
          </PanelSectionRow>
          {atCeiling && (
            <PanelSectionRow>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {tdp.on_ac
                  ? t("tdp.ceiling.charger", { max: activeMax })
                  : t("tdp.ceiling.battery", { max: activeMax })}
              </div>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <Presets
              limits={tdp.limits}
              onAc={tdp.on_ac}
              labels={{
                save: t("tdp.preset.save"),
                balanced: t("tdp.preset.balanced"),
                turbo: t("tdp.preset.turbo"),
              }}
              onPick={onWatts}
            />
          </PanelSectionRow>
          {tdp.supports_advanced && (
            <PanelSectionRow>
              <AdvancedBoost
                levels={view.levels}
                auto={view.auto}
                bounds={{ pl2: tdp.level_limits.pl2, pl3: tdp.level_limits.pl3 }}
                onSetLevels={onSetLevels}
                onResetAuto={onResetAuto}
              />
            </PanelSectionRow>
          )}
        </>
      )}
      <PanelSectionRow>
        <ToggleField
          label={t("tdp.auto.title")}
          description={t("tdp.auto.hint")}
          checked={isAutoOn}
          onChange={onAutoTdp}
        />
      </PanelSectionRow>
    </>
  );
};
