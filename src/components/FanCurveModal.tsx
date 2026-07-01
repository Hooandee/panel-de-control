import { FC } from "react";
import { ModalRoot, showModal } from "@decky/ui";

import { useI18n } from "../i18n";
import { useFanCurve } from "../fans/useFanCurve";
import { useFanSuggestion } from "../fans/useFanSuggestion";
import { FanCurveEditor } from "./FanCurveEditor";
import { theme } from "./../theme";

/**
 * Body of the full-screen fan-curve editor. Runs its OWN useFanCurve (showModal
 * renders in a separate React root, so it can't share the section's hook) — the
 * backend RPCs are the source of truth, and the section refreshes on close (via
 * showModal's fnOnClose). The live-temp marker is a snapshot passed at open time:
 * the modal is short-lived, so re-polling the monitor here would just duplicate
 * the section's still-running poll for no real benefit.
 */
const FanCurveModalBody: FC<{ liveTemp: number | null }> = ({ liveTemp }) => {
  const { t } = useI18n();
  const control = useFanCurve();
  const { suggestion } = useFanSuggestion(control.game?.appid ?? null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("fans.curve.title")}</div>
      <div style={{ maxWidth: 760, width: "100%", margin: "0 auto" }}>
        <FanCurveEditor control={control} liveTemp={liveTemp} suggestion={suggestion} expanded />
      </div>
    </div>
  );
};

// showModal injects `closeModal` into this top-level element; ModalRoot consumes
// it (X icon / B button). useI18n degrades gracefully outside the provider, so
// no per-modal i18n re-wrap is needed.
const FanCurveModal: FC<{ liveTemp: number | null; closeModal?: () => void }> = ({ liveTemp, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FanCurveModalBody liveTemp={liveTemp} />
  </ModalRoot>
);

/** Open the big-screen curve editor. `onClosed` re-syncs the inline card; the
 *  live-temp marker is seeded from the section's current reading. */
export function openFanCurveModal(liveTemp: number | null, onClosed: () => void): void {
  showModal(<FanCurveModal liveTemp={liveTemp} />, window, { fnOnClose: onClosed });
}
