import { PanelSectionRow, SliderField, Spinner } from "@decky/ui";
import { FC } from "react";

import { TdpState, TdpScope } from "../api";
import { useI18n } from "../i18n";
import { fraction, zoneFor } from "../tdp/logic";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  onScope: (scope: TdpScope) => void;
  onWatts: (watts: number) => void;
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, onScope, onWatts }) => {
  const { t } = useI18n();

  if (!tdp) return <Spinner />;

  if (!tdp.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  }

  const displayWatts = scope === "global" ? tdp.global_watts : tdp.watts;
  const zone = zoneFor(fraction(displayWatts, tdp.limits.min, tdp.limits.max_ac));

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
          watts={displayWatts}
          limits={tdp.limits}
          onAc={tdp.on_ac}
          zoneLabel={t(`tdp.zone.${zone.key}`)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          value={displayWatts}
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
    </>
  );
};
