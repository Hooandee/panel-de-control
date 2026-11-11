import { useEffect, useRef, useState, useSyncExternalStore, type FC } from "react";

import { getUpscalerLive, type UpscalerKey } from "../api";
import { useI18n } from "../i18n";
import { pressUpscalerKeyInGame } from "./gameHotkey";
import { fpsCounterSnapshot, subscribeFpsCounter, toggleFpsCounter } from "./fpsCounter";
import { Label, ListCard, ListRow, Note } from "./parts";

const POLL_MS = 1500;

export interface UpscalerLive {
  fps: number | null;
  render: number | null;
  output: number | null;
  generating: boolean | null;
  canPause: boolean;
  active: boolean;
}

/** What the running game reports through OptiScaler's log, polled while the page is open. */
export function useUpscalerLive(appid: string, enabled: boolean, onActive?: () => void): [UpscalerLive, (generating: boolean | null) => void] {
  const [live, setLive] = useState<UpscalerLive>({ fps: null, render: null, output: null, generating: null, canPause: true, active: false });
  const reported = useRef(false);
  const activeRef = useRef(onActive);
  activeRef.current = onActive;
  const pending = !!onActive;

  useEffect(() => {
    reported.current = false;
  }, [pending]);

  useEffect(() => {
    reported.current = false;
    setLive({ fps: null, render: null, output: null, generating: null, canPause: true, active: false });
    if (!enabled) return;
    let alive = true;
    const read = async () => {
      const next = await getUpscalerLive(appid).catch(() => null);
      if (!alive || !next) return;
      if (next.result === "active" && activeRef.current && !reported.current) {
        reported.current = true;
        activeRef.current?.();
      }
      setLive({
        fps: next.fps ?? null,
        render: next.resolution?.render[1] ?? null,
        output: next.resolution?.output[1] ?? null,
        generating: next.fg ?? null,
        canPause: next.fg_toggle !== false,
        active: next.result === "active",
      });
    };
    void read();
    const timer = window.setInterval(read, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [appid, enabled]);

  return [live, (generating) => setLive((last) => ({ ...last, generating }))];
}

/** Tools that only make sense with the game open; OptiScaler's hotkeys for devices without a keyboard. */
export const DuringPlay: FC<{
  appid: string;
  optiscaler: boolean;
  /** False where OptiScaler runs its old menu, which never draws the FPS counter (RE Engine games). */
  fpsCounter?: boolean;
  fg: boolean;
  live: UpscalerLive;
  onGenerating: (generating: boolean | null) => void;
  onCompare: () => void;
}> = ({ appid, optiscaler, fpsCounter = true, fg, live, onGenerating, onCompare }) => {
  const { t } = useI18n();
  const counter = useSyncExternalStore(subscribeFpsCounter, () => fpsCounterSnapshot(appid));
  const [pressing, setPressing] = useState<UpscalerKey | null>(null);
  const [failed, setFailed] = useState(false);

  const press = async (action: UpscalerKey) => {
    if (action === "fps") {
      await toggleFpsCounter(appid, () => pressUpscalerKeyInGame(appid, action));
      return;
    }
    setPressing(action);
    setFailed(false);
    try {
      await pressUpscalerKeyInGame(appid, action);
      if (action === "fg") onGenerating(live.generating === null ? null : !live.generating);
    } catch {
      setFailed(true);
    } finally {
      setPressing(null);
    }
  };

  return (
    <>
      <Label>{t("up.play.title")}</Label>
      <ListCard>
        {optiscaler && fpsCounter && (
          <ListRow first label={t("up.play.fps")} on={counter.on} busy={counter.busy} disabled={pressing !== null}
            onPress={() => void press("fps")} />
        )}
        <ListRow first={!(optiscaler && fpsCounter)} label={t("up.play.compare")} chevron onPress={onCompare} />
        {optiscaler && (
          <ListRow label={t("up.play.menu")} detail={t("up.play.menu.detail")} busy={pressing === "menu"}
            disabled={counter.busy || (pressing !== null && pressing !== "menu")} onPress={() => void press("menu")} />
        )}
        {fg && live.canPause && (
          <ListRow label={t("up.play.pause")} on={live.generating === false} busy={pressing === "fg"}
            disabled={counter.busy || (pressing !== null && pressing !== "fg")} onPress={() => void press("fg")} />
        )}
      </ListCard>
      {(failed || counter.failed) && <Note tone="warn">{t("up.live.failed")}</Note>}
    </>
  );
};
