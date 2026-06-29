import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";
import { LuSun, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { ValueBar } from "../components/ValueBar";
import { useBrightness } from "../system/useBrightness";
import { useVolume } from "../system/useVolume";

/** Quick system controls: brightness + volume, with the exact value visible. */
export const SistemaSection: FC = () => {
  const { t } = useI18n();
  const brightness = useBrightness();
  const volume = useVolume();

  return (
    <>
      <PanelSectionRow>
        <ValueBar
          icon={<LuSun size={16} />}
          label={t("system.brightness")}
          percent={brightness.percent}
          onChange={brightness.set}
          disabled={!brightness.supported}
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
          unavailableLabel={t("system.unavailable")}
        />
      </PanelSectionRow>
    </>
  );
};
