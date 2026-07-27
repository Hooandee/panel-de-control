import { FC } from "react";

import { TdpSection } from "../components/TdpSection";
import { GpuClockCard } from "../components/GpuClockCard";
import { AutoTdpToggle } from "../components/AutoTdpToggle";
import { usePotencia } from "../tdp/potenciaContext";
import { registerBlock } from "../customize/blocks";

const TdpCoreBlock: FC = () => {
  const c = usePotencia();
  // Auto-TDP module off → the loop is stopped; show manual, not the raw flag.
  const power = c.power && !c.autoTdpEnabled ? { ...c.power, auto_tdp: false } : c.power;
  return (
    <TdpSection
      tdp={c.tdp}
      scope={c.scope}
      game={c.game}
      power={power}
      onScope={c.onScope}
      onWatts={c.onWatts}
      onSetLevels={c.onSetLevels}
      onSetMode={c.onSetMode}
      onApplySuggestion={c.onApplySuggestion}
      onFirmwareMode={c.onFirmwareMode}
      monitorOnly={c.monitorOnly}
      onReactivate={c.onReactivate}
      presets={c.presets}
      refreshPresets={c.refreshPresets}
      onApplyPreset={c.onApplyPreset}
    />
  );
};

const GpuBlock: FC = () => {
  const { scope, game, monitorOnly } = usePotencia();
  if (monitorOnly) return null;
  return <GpuClockCard scope={scope} appid={game?.appid ?? null} />;
};

const AutoTdpBlock: FC = () => {
  const { power, onAutoTdpToggle, autoTdpEnabled, monitorOnly } = usePotencia();
  if (monitorOnly || !autoTdpEnabled) return null;
  return <AutoTdpToggle checked={power?.auto_tdp ?? false} onChange={onAutoTdpToggle} />;
};

export function registerPowerBlocks(): void {
  registerBlock("tdp", { sectionId: "power", Component: TdpCoreBlock });
  registerBlock("gpu", { sectionId: "power", Component: GpuBlock });
  // Availability = hardware capability, not the module on/off (block self-gates).
  registerBlock("autoTdp", {
    sectionId: "power",
    Component: AutoTdpBlock,
    useAvailable: () => !!usePotencia().tdp?.supported,
  });
}
