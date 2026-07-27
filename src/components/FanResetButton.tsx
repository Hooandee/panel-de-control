import { FC, useEffect, useRef, useState } from "react";
import { DialogButton } from "@decky/ui";
import { LuTriangleAlert, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useMountedRef } from "../hooks/useMountedRef";
import { theme } from "../theme";

/**
 * Recover a wedged software-loop fan control: hand the fan back to firmware, then
 * re-apply the stored curve. Shown for any backend that can wedge (Deck, Legion EC,
 * generic PWM). The status reflects the backend's reset_ok.
 */
// Bound the pending state: the reset recovers a wedged backend, so a promise that
// never resolves (stuck executor, lost RPC response) must not disable the button
// forever. Generous: a Deck reset chains a few systemctl calls (~10s each) plus the
// re-apply, so a valid one can take ~30s — the watchdog must not cut it short.
const RESET_TIMEOUT_MS = 45000;

export const FanResetButton: FC<{ onReset: () => Promise<boolean> }> = ({ onReset }) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<"idle" | "pending" | "ok" | "fail">("idle");
  // Atomic guard: `status` updates asynchronously, so a fast double-activate could
  // fire two resets before the "pending" state lands. A ref flips synchronously.
  const busy = useRef(false);
  const alive = useMountedRef();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdog = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    if (watchdog.current) clearTimeout(watchdog.current);
  }, []);
  const handleReset = () => {
    if (busy.current) return;
    busy.current = true;
    // Cancel a prior reset's "return to idle" timer so it can't fire during this one
    // and wipe the "pending" state mid-flight.
    if (timer.current) clearTimeout(timer.current);
    setStatus("pending");
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;   // ignore a late resolve after the watchdog fired (or vice versa)
      settled = true;
      busy.current = false;
      if (watchdog.current) clearTimeout(watchdog.current);
      if (!alive.current) return;
      setStatus(ok ? "ok" : "fail");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => { if (alive.current) setStatus("idle"); }, 2500);
    };
    watchdog.current = setTimeout(() => finish(false), RESET_TIMEOUT_MS);
    onReset().then((ok) => finish(ok)).catch(() => finish(false));
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <DialogButton style={{ width: "100%" }} disabled={status === "pending"} onClick={handleReset}>
        {t("fans.experimental.reset")}
      </DialogButton>
      {status === "ok" ? (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.ok, lineHeight: 1.4 }}>
          <LuCheck size={14} /> {t("fans.experimental.resetDone")}
        </div>
      ) : status === "fail" ? (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.warn, lineHeight: 1.4 }}>
          <LuTriangleAlert size={14} /> {t("fans.experimental.resetFail")}
        </div>
      ) : (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
          {status === "pending" ? t("fans.experimental.resetPending") : t("fans.experimental.resetNote")}
        </div>
      )}
    </div>
  );
};
