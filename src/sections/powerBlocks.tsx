import { FC } from "react";

import { TdpSection } from "../components/TdpSection";
import { AutoTdpToggle } from "../components/AutoTdpToggle";
import { usePotencia } from "../tdp/potenciaContext";
import { registerBlock } from "../customize/blocks";
import { useDesktopState } from "../desktop/useDesktop";
import { desktopUiActive } from "../desktop/presentation";
import { DesktopPowerCard, DesktopPowerRecoveryCard } from "../components/DesktopPowerCard";

const TdpCoreBlock: FC = () => {
  const c = usePotencia();
  const desktop = useDesktopState();
  if (desktop.error) return <DesktopPowerRecoveryCard kind="unavailable" onRetry={desktop.refresh} />;
  if (desktopUiActive(desktop.state)) return <DesktopPowerCard />;
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

const AutoTdpBlock: FC = () => {
  const { power, onAutoTdpToggle, autoTdpEnabled, monitorOnly } = usePotencia();
  if (monitorOnly || !autoTdpEnabled) return null;
  return <AutoTdpToggle checked={power?.auto_tdp ?? false} onChange={onAutoTdpToggle} />;
};

export function registerPowerBlocks(): void {
  registerBlock("tdp", { sectionId: "power", Component: TdpCoreBlock });
  registerBlock("desktopPower", { sectionId: "power", Component: DesktopPowerCard });
  // Availability = hardware capability, not the module on/off (block self-gates).
  registerBlock("autoTdp", {
    sectionId: "power",
    Component: AutoTdpBlock,
    useAvailable: () => {
      const tdp = usePotencia().tdp;
      return !!tdp?.supported && tdp.supports_auto_tdp;
    },
  });
}
