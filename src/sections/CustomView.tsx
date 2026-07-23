import { FC, ReactNode, useMemo } from "react";

import { Block, getBlockDef, BLOCK_GAP } from "../customize/blocks";
import { providersFor } from "../customize/views";
import { useViews } from "../customize/viewStore";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { POWER_TAB } from "../customize/manifest";
import { usePotencia } from "../tdp/potenciaContext";
import { TdpMonitorNotice } from "../components/TdpMonitorNotice";
import { SECTION_PROVIDERS } from "./providerMounts";

// Keeps a power-only view (GPU clock / Auto-TDP, no core tdp block) from rendering
// blank in monitor mode. Only mounted when the view has power blocks, so its provider
// is present. Skipped when TDP is unsupported (nothing to reactivate).
const PowerMonitorFallback: FC = () => {
  const { monitorOnly, onReactivate, tdp } = usePotencia();
  if (!tdp?.supported || !monitorOnly) return null;
  return <TdpMonitorNotice onReactivate={onReactivate} />;
};

export const CustomView: FC<{ viewId: string }> = ({ viewId }) => {
  const views = useViews();
  const disabled = useModules();
  const view = views.find((v) => v.id === viewId);
  // Drop blocks whose section module is off. Potencia is the exception (mirrors the
  // shell): master-off means monitor-only, not gone, so its blocks stay.
  const blocks = useMemo(
    () => (view?.blocks ?? []).filter((id) => {
      const sid = getBlockDef(id)?.sectionId;
      return !sid || sid === POWER_TAB || effectiveEnabled(sid, disabled);
    }),
    [view, disabled],
  );

  const sections = useMemo(
    () => providersFor(blocks, (id) => getBlockDef(id)?.sectionId),
    [blocks],
  );

  // Power blocks but no core "tdp" block (which carries the notice itself) → add the
  // fallback so a monitor-mode view isn't blank.
  const needsPowerFallback =
    blocks.some((id) => getBlockDef(id)?.sectionId === POWER_TAB) && !blocks.includes("tdp");

  const content: ReactNode = (
    <div style={{ display: "flex", flexDirection: "column", gap: BLOCK_GAP }}>
      {needsPowerFallback && <PowerMonitorFallback />}
      {blocks.map((id) => (
        <Block key={id} id={id} />
      ))}
    </div>
  );

  return sections.reduceRight<ReactNode>((acc, s) => {
    const Mount = SECTION_PROVIDERS[s];
    return Mount ? <Mount>{acc}</Mount> : acc;
  }, content);
};
