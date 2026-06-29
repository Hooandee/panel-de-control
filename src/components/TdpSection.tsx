import { PanelSectionRow, SliderField, Spinner } from "@decky/ui";
import { FC } from "react";

import { TdpState, TdpScope } from "../api";
import { useI18n } from "../i18n";
import { fraction, zoneFor } from "../tdp/logic";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";
import { AdvancedBoost } from "./AdvancedBoost";

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  onScope: (scope: TdpScope) => void;
  onWatts: (watts: number) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onResetAuto: () => void;
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, onScope, onWatts, onSetLevels, onResetAuto }) => {
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
  const zone = zoneFor(fraction(view.watts, tdp.limits.min, tdp.limits.max_ac));

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
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          value={view.watts}
          min={tdp.limits.min}
          max={tdp.limits.max_ac}
          step={1}
          showValue
          onChange={onWatts}
        />
      </PanelSectionRow>
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
  );
};
