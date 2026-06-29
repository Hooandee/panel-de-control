import { PanelSectionRow, SliderField, Spinner, ToggleField } from "@decky/ui";
import { FC } from "react";

import { TdpState, TdpScope, PowerDraw } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { fraction, zoneFor } from "../tdp/logic";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";
import { AdvancedBoost } from "./AdvancedBoost";

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
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, power, onScope, onWatts, onSetLevels, onResetAuto, onAutoTdp }) => {
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
        />
      </PanelSectionRow>
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
