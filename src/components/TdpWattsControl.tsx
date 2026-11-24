import { FC } from "react";
import { PanelSectionRow, SliderField } from "@decky/ui";

import type { PowerDraw, TdpScope, TdpState } from "../api";
import { useI18n } from "../i18n";
import { wattsRange } from "../tdp/extraZone";
import { Loading } from "./Loading";
import { TdpMonitorNotice } from "./TdpMonitorNotice";

interface Props {
  tdp: TdpState | null;
  scope: TdpScope;
  power: PowerDraw | null;
  onWatts: (watts: number) => void;
  monitorOnly: boolean;
  steamControlled: boolean;
  onReactivate: () => void | Promise<void>;
}

const DISABLED_OPACITY = 0.45;

// Only the sustained-limit slider of the TDP section, for custom views.
export const TdpWattsControl: FC<Props> = ({ tdp, scope, power, onWatts, monitorOnly, steamControlled, onReactivate }) => {
  const { t } = useI18n();
  if (!tdp) return <Loading />;
  if (!tdp.supported) return null;
  const { requestMin, sliderMax } = wattsRange(tdp);
  const stored = scope === "global" ? tdp.global_watts : tdp.watts;
  const auto = !monitorOnly && (power?.auto_tdp ?? false);
  const shown = auto ? (power?.setpoint ?? stored) : stored;
  const locked = monitorOnly || auto;
  return (
    <>
      {monitorOnly && (
        <PanelSectionRow>
          <TdpMonitorNotice steam={steamControlled} onReactivate={onReactivate} />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <div style={locked ? { opacity: DISABLED_OPACITY } : undefined}>
          <SliderField
            label={t("customize.block.tdpWatts")}
            value={Math.min(shown, sliderMax)}
            min={requestMin}
            max={sliderMax}
            step={1}
            showValue
            disabled={locked}
            onChange={onWatts}
          />
        </div>
      </PanelSectionRow>
    </>
  );
};
