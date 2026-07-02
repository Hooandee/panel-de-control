import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";
import { LuSun, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { ValueBar } from "../components/ValueBar";
import { BatteryCard } from "../components/BatteryCard";
import { useBrightness, useVolume } from "../system/useScalar";
import { useBattery } from "../system/useBattery";

/** System controls: battery (state/health/charge limit) then brightness + volume. */
export const SistemaSection: FC = () => {
  const { t } = useI18n();
  const brightness = useBrightness();
  const volume = useVolume();
  const battery = useBattery();

  return (
    <>
      {battery.state && (
        <BatteryCard state={battery.state} onSetLimit={battery.setLimit} />
      )}
      <PanelSectionRow>
        <ValueBar
          icon={<LuSun size={16} />}
          label={t("system.brightness")}
          percent={brightness.percent}
          onChange={brightness.set}
          disabled={!brightness.supported}
          loading={brightness.loading}
          unavailableLabel={t("system.unavailable")}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ValueBar
          icon={<LuVolume2 size={16} />}
          label={t("system.volume")}
          percent={volume.percent}
          onChange={volume.set}
          disabled={!volume.supported}
          loading={volume.loading}
          unavailableLabel={t("system.unavailable")}
        />
      </PanelSectionRow>
    </>
  );
};
