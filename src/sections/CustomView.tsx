import { FC, ReactNode, useMemo } from "react";

import { Block, getBlockDef, BLOCK_GAP } from "../customize/blocks";
import { providersFor } from "../customize/views";
import { useViews } from "../customize/viewStore";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { blockAvailableInMode, POWER_TAB } from "../customize/manifest";
import { useDesktopState } from "../desktop/useDesktop";
import { usePotencia } from "../tdp/potenciaContext";
import { TdpMonitorNotice } from "../components/TdpMonitorNotice";
import { PotenciaProviderMount, SECTION_PROVIDERS } from "./providerMounts";

const POWER_PROFILE_BLOCKS = new Set(["tdp", "autoTdp", "steamPerformance"]);

const PowerMonitorFallback: FC = () => {
  const { monitorOnly, onReactivate, tdp } = usePotencia();
  if (!tdp?.supported || !monitorOnly) return null;
  return <TdpMonitorNotice onReactivate={onReactivate} />;
};

export const CustomView: FC<{ viewId: string }> = ({ viewId }) => {
  const views = useViews();
  const disabled = useModules();
  const desktopMode = !!useDesktopState().state?.enabled;
  const view = views.find((v) => v.id === viewId);
  // Drop blocks whose section module is off. Potencia is the exception (mirrors the
  // shell): master-off means monitor-only, not gone, so its blocks stay.
  const blocks = useMemo(
    () => (view?.blocks ?? []).filter((id) => {
      if (!blockAvailableInMode(id, desktopMode)) return false;
      const sid = getBlockDef(id)?.sectionId;
      return !sid || sid === POWER_TAB || effectiveEnabled(sid, disabled);
    }),
    [view, disabled, desktopMode],
  );

  const sections = useMemo(
    () => providersFor(blocks, (id) => getBlockDef(id)?.sectionId),
    [blocks],
  );

  const needsPowerFallback = blocks.includes("autoTdp") && !blocks.includes("tdp");
  const needsPowerProfileSelector = blocks.some((id) => POWER_PROFILE_BLOCKS.has(id));

  const content: ReactNode = (
    <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
      {needsPowerFallback && <PowerMonitorFallback />}
      {blocks.map((id) => (
        <Block key={id} id={id} />
      ))}
    </div>
  );

  return sections.reduceRight<ReactNode>((acc, s) => {
    if (s === POWER_TAB) {
      return (
        <PotenciaProviderMount showProfileSelector={needsPowerProfileSelector}>
          {acc}
        </PotenciaProviderMount>
      );
    }
    const Mount = SECTION_PROVIDERS[s];
    return Mount ? <Mount>{acc}</Mount> : acc;
  }, content);
};
