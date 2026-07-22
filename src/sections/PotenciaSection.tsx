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

export const PotenciaSection: FC = () => {
  const tdpCtl = useTdp();
  const { tdp, refresh } = tdpCtl;
  const conflict = useTdpConflict(tdp?.supported ?? false, tdp?.tdp_control_enabled ?? true);
  const disabled = useModules();
  const autoTdpEnabled = effectiveEnabled("autoTdp", disabled);

  const shownTakeover = useRef(false);
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
      {!conflict.monitorOnly && <SectionView sectionId="power" />}
    </PotenciaProvider>
  );
};
