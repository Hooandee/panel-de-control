import { FC } from "react";
import { Focusable, ModalRoot, showModal } from "@decky/ui";

import { useI18n } from "../i18n";
import { useEq } from "../audio/useEq";
import { EqCurveGraph } from "./EqCurveGraph";
import { segmentItemStyle } from "./segmented";
import { theme } from "../theme";

// Zone labels sit under the frequency axis at the center of each tone region.
const ZONE_BANDS = { graves: 2, voces: 6, agudos: 8 } as const;

/**
 * Full-screen EQ editor. Runs its OWN useEq (showModal renders in a separate React root,
 * so it can't share the section's hook) — the RPCs are the source of truth and the section
 * refreshes on close (via showModal's fnOnClose).
 */
const EqCurveModalBody: FC = () => {
  const { t } = useI18n();
  const { state, onBands, onReset } = useEq();
  if (!state) return null;

  const ceilings = state.route === "headphone" ? undefined : state.safe_limits.bands;
  const zones = [
    { label: t("audio.tone.graves"), band: ZONE_BANDS.graves },
    { label: t("audio.tone.voces"), band: ZONE_BANDS.voces },
    { label: t("audio.tone.agudos"), band: ZONE_BANDS.agudos },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("audio.advanced")}</div>
      <div style={{ maxWidth: 760, width: "100%", margin: "0 auto" }}>
        <EqCurveGraph gains={state.gains} editable onChange={onBands} ceilings={ceilings} guard={state.guard} zones={zones} yTitle={t("audio.axis.y")} />
        <Focusable
          style={{ ...segmentItemStyle(false), textAlign: "center", padding: "6px 12px", marginTop: 10 }}
          onActivate={onReset}
          onClick={onReset}
        >
          {t("audio.reset")}
        </Focusable>
      </div>
    </div>
  );
};

const EqCurveModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <EqCurveModalBody />
  </ModalRoot>
);

/** Open the big-screen EQ editor; `onClosed` re-syncs the inline section. */
export function openEqCurveModal(onClosed: () => void): void {
  showModal(<EqCurveModal />, window, { fnOnClose: onClosed });
}
