import { FC, useEffect, useRef } from "react";
import { PanelSectionRow } from "@decky/ui";

import { setSeenTdpConflictTakeover } from "../api";
import { TdpConflictCard } from "../components/TdpConflictCard";
import { openTdpConflictModal } from "../components/TdpConflictModal";
import { Block, SectionView } from "../customize/blocks";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { useTdp } from "../tdp/useTdp";
import { useTdpConflict } from "../tdp/useTdpConflict";
import { PotenciaProvider } from "../tdp/potenciaContext";
import "./powerBlocks"; // registers the Potencia blocks

/**
 * Power section: owns the TDP state (via useTdp) and renders the power-arc core as
 * fixed chrome, with the GPU-clock and Auto‑TDP blocks below it from the registry.
 * The conflict card + first-run take-over modal are chrome that governs the core.
 */
export const PotenciaSection: FC = () => {
  const tdpCtl = useTdp();
  const { tdp, refresh } = tdpCtl;
  const conflict = useTdpConflict(tdp?.supported ?? false, tdp?.tdp_control_enabled ?? true);
  const disabled = useModules();
  const autoTdpEnabled = effectiveEnabled("autoTdp", disabled);

  // Fires the first-run take-over modal at most once per mount.
  const shownTakeover = useRef(false);
  // Keep the latest conflict actions reachable from the modal callback without
  // re-arming the first-run effect.
  const conflictRef = useRef(conflict);
  conflictRef.current = conflict;
  useEffect(() => {
    if (!tdp || shownTakeover.current) return;
    if (conflict.conflict && !tdp.seen_tdp_conflict_takeover) {
      shownTakeover.current = true;
      openTdpConflictModal(() => void conflictRef.current.takeAll());
      setSeenTdpConflictTakeover(true).then(() => refresh()).catch(() => {});
    }
  }, [conflict.conflict, tdp, refresh]);

  return (
    <PotenciaProvider value={{ ...tdpCtl, monitorOnly: conflict.monitorOnly, autoTdpEnabled }}>
      {conflict.conflict && (
        <PanelSectionRow>
          <TdpConflictCard
            rivals={conflict.rivals}
            onDisableSdtdp={() => void conflict.disableSdtdp()}
            onTakeHhd={() => void conflict.takeHhd()}
          />
        </PanelSectionRow>
      )}
      <Block id="tdp" />
      {/* Every write control drops away in monitor-only mode (we've stepped aside). */}
      {!conflict.monitorOnly && <SectionView sectionId="power" />}
    </PotenciaProvider>
  );
};
