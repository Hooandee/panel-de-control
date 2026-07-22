import { FC } from "react";

import { TdpSection } from "../components/TdpSection";
import { GpuClockCard } from "../components/GpuClockCard";
import { AutoTdpToggle } from "../components/AutoTdpToggle";
import { usePotencia } from "../tdp/potenciaContext";
import { registerBlock } from "../customize/blocks";

const TdpCoreBlock: FC = () => {
  const c = usePotencia();
  return (
    <TdpSection
      tdp={c.tdp}
      scope={c.scope}
      game={c.game}
      power={c.power}
      onScope={c.onScope}
      onWatts={c.onWatts}
      onSetLevels={c.onSetLevels}
      onSetMode={c.onSetMode}
      onApplySuggestion={c.onApplySuggestion}
      onFirmwareMode={c.onFirmwareMode}
      monitorOnly={c.monitorOnly}
    />
  );
};

const GpuBlock: FC = () => {
  const { scope, game } = usePotencia();
  return <GpuClockCard scope={scope} appid={game?.appid ?? null} />;
};

const AutoTdpBlock: FC = () => {
  const { power, onAutoTdpToggle } = usePotencia();
  return <AutoTdpToggle checked={power?.auto_tdp ?? false} onChange={onAutoTdpToggle} />;
};

export function registerPowerBlocks(): void {
  registerBlock("tdp", { sectionId: "power", Component: TdpCoreBlock });
  registerBlock("gpu", { sectionId: "power", Component: GpuBlock });
  registerBlock("autoTdp", {
    sectionId: "power",
    Component: AutoTdpBlock,
    useAvailable: () => usePotencia().autoTdpEnabled,
  });
}
