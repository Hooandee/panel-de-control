import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";
import { LuBatteryFull, LuCpu, LuSun, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { ValueBar } from "../components/ValueBar";
import { BatteryCard } from "../components/BatteryCard";
import { CpuCard } from "../components/CpuCard";
import { Collapsible } from "../components/Collapsible";
import { batteryStatusKey } from "../system/battery";
import { useBrightness, useVolume } from "../system/useScalar";
import { useBattery } from "../system/useBattery";
import { useCpu } from "../system/useCpu";

/** System controls: battery + CPU (collapsible, rich) then brightness + volume (simple bars). */
export const SistemaSection: FC = () => {
  const { t } = useI18n();
  const brightness = useBrightness();
  const volume = useVolume();
  const battery = useBattery();
  const cpu = useCpu();

  const b = battery.state?.battery;
  const batterySummary = b?.present
    ? `${b.percent === null ? "—" : `${b.percent}%`} · ${t(`system.battery.${batteryStatusKey(b.status, b.ac_online)}`)}`
    : "—";

  const cs = cpu.state;
  const cpuSummary = cs
    ? `${cs.cores ?? "—"} ${t("system.cpu.coresWord")} · ${t("system.cpu.turbo")} ${cs.boost.enabled ? t("system.on") : t("system.off")}`
    : "—";

  return (
    <>
      {battery.state && (
        <Collapsible icon={<LuBatteryFull size={16} />} title={t("system.battery.title")} summary={batterySummary}>
          <BatteryCard state={battery.state} onSetLimit={battery.setLimit} />
        </Collapsible>
      )}
      {cpu.state && (
        <Collapsible icon={<LuCpu size={16} />} title={t("system.cpu.title")} summary={cpuSummary}>
          <CpuCard state={cpu.state} onSetSmt={cpu.setSmt} onSetBoost={cpu.setBoost} />
        </Collapsible>
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
