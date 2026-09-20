import { FC } from "react";

import { TdpSection } from "../components/TdpSection";
import { AutoTdpCard } from "../components/AutoTdpCard";
import { usePotencia } from "../tdp/potenciaContext";
import { registerBlock } from "../customize/blocks";
import { useDesktopState } from "../desktop/useDesktop";
import { desktopUiActive } from "../desktop/presentation";
import { resolveAutoView } from "../tdp/autoView";
import { DesktopPowerCard, DesktopPowerRecoveryCard } from "../components/DesktopPowerCard";
import { SteamPerformanceCard } from "../components/SteamPerformanceCard";

const TdpCoreBlock: FC = () => {
  const c = usePotencia();
  const desktop = useDesktopState();
  if (desktop.error) return <DesktopPowerRecoveryCard kind="unavailable" onRetry={desktop.refresh} />;
  if (desktopUiActive(desktop.state)) return <DesktopPowerCard />;
  const autoView = c.tdp
    ? resolveAutoView(c.tdp, c.power, c.scope, Boolean(c.game))
    : null;
  const power = autoView?.power && !c.autoTdpEnabled
    ? { ...autoView.power, auto_tdp: false }
    : autoView?.power ?? c.power;
  const tdp = c.tdp && c.autoTdpEnabled && autoView?.hideManualSuggestion
    ? { ...c.tdp, learned: { ...c.tdp.learned, enough: false } }
    : c.tdp;
  return (
    <TdpSection
      tdp={tdp}
      scope={c.scope}
      power={power}
      onWatts={c.onWatts}
      onSetLevels={c.onSetLevels}
      onSetMode={c.onSetMode}
      onApplySuggestion={c.onApplySuggestion}
      onFirmwareMode={c.onFirmwareMode}
      onLowBatteryHold={c.onLowBatteryHold}
      monitorOnly={c.monitorOnly}
      onReactivate={c.onReactivate}
      presets={c.presets}
      refreshPresets={c.refreshPresets}
      onApplyPreset={c.onApplyPreset}
    />
  );
};

const AutoTdpBlock: FC = () => {
  const {
    tdp,
    power,
    scope,
    game,
    onAutoTdpToggle,
    onAutoTargetFps,
    onAutoInitialTdp,
    onAutoMinTdp,
    onAutoMaxTdp,
    autoTdpEnabled,
    monitorOnly,
  } = usePotencia();
  if (monitorOnly || !autoTdpEnabled || !tdp) return null;
  const view = resolveAutoView(tdp, power, scope, Boolean(game));
  return (
    <AutoTdpCard
      config={view.config}
      scope={scope}
      limits={tdp.auto_limits}
      requestLimits={tdp.auto_request_limits}
      onAc={tdp.on_ac}
      maxTargetFps={tdp.auto_target_max_fps}
      live={view.power?.auto ?? null}
      liveApplies={view.liveApplies && Boolean(power?.auto_tdp)}
      onToggle={onAutoTdpToggle}
      onTargetFps={onAutoTargetFps}
      onInitialTdp={onAutoInitialTdp}
      onMinTdp={onAutoMinTdp}
      onMaxTdp={onAutoMaxTdp}
    />
  );
};

const SteamPerformanceBlock: FC = () => {
  const { scope, game } = usePotencia();
  return (
    <SteamPerformanceCard
      profileScope={scope}
      runningGameId={game?.liveAppid ?? null}
    />
  );
};

export function registerPowerBlocks(): void {
  registerBlock("tdp", { sectionId: "power", Component: TdpCoreBlock });
  registerBlock("desktopPower", { sectionId: "power", Component: DesktopPowerCard });
  registerBlock("steamPerformance", {
    sectionId: "power",
    Component: SteamPerformanceBlock,
  });
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
