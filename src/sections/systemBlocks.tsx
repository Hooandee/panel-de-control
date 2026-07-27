import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";
import { LuBatteryFull, LuCpu, LuSun, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { ValueBar } from "../components/ValueBar";
import { BatteryCard } from "../components/BatteryCard";
import { CpuCard } from "../components/CpuCard";
import { EcoCard } from "../components/EcoCard";
import { ColoresCard } from "../components/ColoresCard";
import { Collapsible } from "../components/Collapsible";
import { batteryStatusKey } from "../system/battery";
import { deviceHasRgb } from "../system/colores";
import { useDevice } from "../system/useDevice";
import { useBrightness, useVolume } from "../system/useScalar";
import { useBattery } from "../system/useBattery";
import { useCpu } from "../system/useCpu";
import { useEco } from "../system/useEco";
import { useColores } from "../system/useColores";
import { registerBlock } from "../customize/blocks";
import { useLayout } from "../customize/store";
import { subitemHidden } from "../customize/layout";

const EcoBlock: FC = () => {
  const eco = useEco();
  const brightness = useBrightness();
  if (!eco.state) return null;
  return (
    <EcoCard
      state={eco.state}
      brightnessSupported={brightness.supported}
      onToggle={(en) => eco.toggle(en, brightness.percent)}
    />
  );
};

const BatteryBlock: FC = () => {
  const { t } = useI18n();
  const battery = useBattery();
  const layout = useLayout();
  if (!battery.state) return null;
  const b = battery.state.battery;
  const summary = b?.present
    ? `${b.percent === null ? "—" : `${b.percent}%`} · ${t(`system.battery.${batteryStatusKey(b.status, b.ac_online)}`)}`
    : "—";
  return (
    <Collapsible id="battery" icon={<LuBatteryFull size={16} />} title={t("system.battery.title")} summary={summary}>
      <BatteryCard
        state={battery.state}
        onSetLimit={battery.setLimit}
        hideHealth={subitemHidden(layout.subitems, "battery", "health")}
      />
    </Collapsible>
  );
};

const CpuBlock: FC = () => {
  const { t } = useI18n();
  const cpu = useCpu();
  const cs = cpu.state;
  if (!cs) return null;
  const summary = `${cs.cores ?? "—"} ${t("system.cpu.coresWord")} · ${t("system.cpu.turbo")} ${cs.boost.enabled ? t("system.on") : t("system.off")}`;
  return (
    <Collapsible id="cpu" icon={<LuCpu size={16} />} title={t("system.cpu.title")} summary={summary}>
      <CpuCard state={cs} scope={cpu.scope} game={cpu.game} onScope={cpu.onScope} onSetSmt={cpu.setSmt} onSetBoost={cpu.setBoost} onSetCores={cpu.setCores} />
    </Collapsible>
  );
};

const BrightnessBlock: FC = () => {
  const { t } = useI18n();
  const brightness = useBrightness();
  return (
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
  );
};

const VolumeBlock: FC = () => {
  const { t } = useI18n();
  const volume = useVolume();
  return (
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
  );
};

const ColoresBlock: FC = () => {
  const colores = useColores();
  if (!colores.hasRgb) return null;
  return (
    <ColoresCard
      state={colores.state}
      onInstall={colores.install}
      onOpen={colores.open}
      onOpenStore={colores.openStore}
    />
  );
};

export function registerSystemBlocks(): void {
  registerBlock("eco", { sectionId: "system", Component: EcoBlock });
  registerBlock("battery", { sectionId: "system", Component: BatteryBlock });
  registerBlock("cpu", { sectionId: "system", Component: CpuBlock });
  registerBlock("brightness", { sectionId: "system", Component: BrightnessBlock });
  registerBlock("volume", { sectionId: "system", Component: VolumeBlock });
  registerBlock("colores", {
    sectionId: "system",
    Component: ColoresBlock,
    useAvailable: () => deviceHasRgb(useDevice()),
  });
}
