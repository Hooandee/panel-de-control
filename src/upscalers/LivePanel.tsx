import { useEffect, useRef, useState, type FC } from "react";

import { getUpscalerLive, pressUpscalerKey, type UpscalerKey } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ActionButton, Row } from "./parts";

const POLL_MS = 1500;

/** While the game runs: the real frame rate and OptiScaler's hotkeys, for devices without a keyboard. */
export const LivePanel: FC<{ appid: string; fg: boolean; menu?: boolean; onActive?: () => void }> = ({ appid, fg, menu = true, onActive }) => {
  const { t } = useI18n();
  const [fps, setFps] = useState<number | null>(null);
  const [generating, setGenerating] = useState<boolean | null>(null);
  const [pressing, setPressing] = useState<UpscalerKey | null>(null);
  const [failed, setFailed] = useState(false);

  const reported = useRef(false);
  const activeRef = useRef(onActive);
  activeRef.current = onActive;

  useEffect(() => {
    let alive = true;
    const read = async () => {
      const live = await getUpscalerLive(appid).catch(() => null);
      if (!alive || !live) return;
      if (live.result === "active" && !reported.current) {
        reported.current = true;
        activeRef.current?.();
      }
      setFps(live.fps ?? null);
      setGenerating(live.fg ?? null);
    };
    void read();
    const timer = window.setInterval(read, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [appid]);

  const press = async (action: UpscalerKey) => {
    setPressing(action);
    setFailed(false);
    try {
      await pressUpscalerKey(appid, action);
      if (action === "fg") setGenerating((value) => (value === null ? null : !value));
    } catch {
      setFailed(true);
    } finally {
      setPressing(null);
    }
  };

  return (
    <div style={{ ...theme.card, padding: `${theme.space.sm}px ${theme.space.md}px`, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs }}>
        <span style={{ fontWeight: 700, fontSize: theme.font.body + 6, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
          {fps === null ? "–" : Math.round(fps)}
        </span>
        <span style={{ flex: 1, fontSize: theme.font.caption + 1, color: theme.color.textMuted }}>{t("up.live.fps")}</span>
        {fg && generating !== null && (
          <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textPrimary }}>
            {t(generating ? "up.live.generating" : "up.live.paused")}
          </span>
        )}
      </div>
      <Row>
        {menu && <ActionButton label={t("up.live.menu")} onPress={() => press("menu")} busy={pressing === "menu"} disabled={pressing !== null} />}
        {fg && (
          <ActionButton
            label={t(generating === false ? "up.live.resume" : "up.live.pause")}
            onPress={() => press("fg")}
            busy={pressing === "fg"}
            disabled={pressing !== null}
          />
        )}
      </Row>
      {menu && (
        <Row>
          <ActionButton label={t("up.live.fps.counter")} onPress={() => press("fps")} busy={pressing === "fps"} disabled={pressing !== null} />
          <ActionButton label={t("up.live.fps.style")} onPress={() => press("fps_style")} busy={pressing === "fps_style"} disabled={pressing !== null} />
        </Row>
      )}
      {failed && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("up.live.failed")}</span>}
    </div>
  );
};
