import { FC, ReactNode, useEffect, useRef } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";

import { setSeenTdpConflictTakeover } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useColor } from "../display/useColor";
import { useHdr } from "../display/useHdr";
import { useNight } from "../display/useNight";
import { isNativeColor } from "../display/color";
import { PantallaProvider } from "../display/pantallaContext";
import { useController } from "../mandos/useController";
import { MandosProvider } from "../mandos/mandosContext";
import { useTdp } from "../tdp/useTdp";
import { useTdpConflict } from "../tdp/useTdpConflict";
import { PotenciaProvider } from "../tdp/potenciaContext";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { TdpConflictCard } from "../components/TdpConflictCard";
import { openTdpConflictModal } from "../components/TdpConflictModal";
import { Loading } from "../components/Loading";

// Provider mounts own a section's shared hooks and expose them via context, so the
// section AND any custom view hosting its blocks share one instance. Safety/honesty
// chrome tied to the machinery travels with the mount (Pantalla confirm+perf,
// Potencia conflict card); the section-only chrome (scope tab, unsupported note)
// stays in the section body.

export const PantallaProviderMount: FC<{ children: ReactNode }> = ({ children }) => {
  const { t } = useI18n();
  const color = useColor();
  const { state, revertIn, confirmCalibration } = color;
  const hdr = useHdr(color.scope, color.game?.appid ?? null);
  const night = useNight();
  // Always provide (blocks self-gate on state), so a still-loading color panel
  // doesn't blank sibling blocks in a custom view.
  const active = !!state && !isNativeColor(state);
  return (
    <PantallaProvider value={{ color, hdr, night }}>
      {revertIn !== null && (
        <PanelSectionRow>
          <div style={{
            display: "flex", alignItems: "center", gap: theme.space.sm,
            borderRadius: theme.radius.md, padding: theme.space.md, marginBottom: theme.space.card,
            background: "rgba(255,180,84,0.14)", boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
                {t("display.confirm.title")}
              </div>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {t("display.confirm.desc", { s: revertIn })}
              </div>
            </div>
            <Focusable
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                padding: "8px 14px", borderRadius: theme.radius.sm,
                background: theme.color.accent, color: "#ffffff", fontWeight: 700,
                fontSize: theme.font.body, cursor: "pointer", whiteSpace: "nowrap",
              }}
              onActivate={confirmCalibration} onClick={confirmCalibration}
            >
              {t("display.confirm.save")}
            </Focusable>
          </div>
        </PanelSectionRow>
      )}
      {state?.perf_cost && active && (
        <PanelSectionRow>
          <div style={{
            fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4,
            padding: "8px 10px", margin: "2px 0 8px",
            borderRadius: theme.radius.sm, background: "rgba(255,255,255,0.04)",
          }}>
            {t("display.perf_note", { device: state.device_name })}
          </div>
        </PanelSectionRow>
      )}
      {children}
    </PantallaProvider>
  );
};

export const MandosProviderMount: FC<{ children: ReactNode }> = ({ children }) => {
  const controller = useController();
  if (!controller.config) return <Loading />;
  return <MandosProvider value={controller}>{children}</MandosProvider>;
};

export const PotenciaProviderMount: FC<{ children: ReactNode }> = ({ children }) => {
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
      {children}
    </PotenciaProvider>
  );
};

export const SECTION_PROVIDERS: Record<string, FC<{ children: ReactNode }>> = {
  display: PantallaProviderMount,
  mandos: MandosProviderMount,
  power: PotenciaProviderMount,
};
