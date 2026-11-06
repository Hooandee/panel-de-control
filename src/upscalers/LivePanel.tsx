import { Navigation } from "@decky/ui";
import { useEffect, useRef, useState, type FC } from "react";

import { getUpscalerLive, pressUpscalerKey, type UpscalerKey } from "../api";
import { useI18n } from "../i18n";
import { holdPage } from "./pageMemory";
import { Label, ListCard, ListRow, Note } from "./parts";

const POLL_MS = 1500;

export interface UpscalerLive {
  fps: number | null;
  render: number | null;
  output: number | null;
  generating: boolean | null;
  canPause: boolean;
}

/** What the running game reports through OptiScaler's log, polled while the page is open. */
export function useUpscalerLive(appid: string, enabled: boolean, onActive?: () => void): [UpscalerLive, (generating: boolean | null) => void] {
  const [live, setLive] = useState<UpscalerLive>({ fps: null, render: null, output: null, generating: null, canPause: true });
  const reported = useRef(false);
  const activeRef = useRef(onActive);
  activeRef.current = onActive;
  const pending = !!onActive;

  useEffect(() => {
    reported.current = false;
  }, [pending]);

  useEffect(() => {
    reported.current = false;
    setLive({ fps: null, render: null, output: null, generating: null, canPause: true });
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
  fg: boolean;
  live: UpscalerLive;
  onGenerating: (generating: boolean | null) => void;
  onCompare: () => void;
}> = ({ appid, optiscaler, fg, live, onGenerating, onCompare }) => {
  const { t } = useI18n();
  const [counter, setCounter] = useState(false);
  const [pressing, setPressing] = useState<UpscalerKey | null>(null);
  const [failed, setFailed] = useState(false);

  const press = async (action: UpscalerKey) => {
    setPressing(action);
    setFailed(false);
    try {
      // gamescope hands the key to the focused window: with the QAM open, Steam keeps it.
      holdPage();
      Navigation.CloseSideMenus();
      await pressUpscalerKey(appid, action);
      if (action === "fps") setCounter((on) => !on);
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
        {optiscaler && (
          <ListRow first label={t("up.play.fps")} on={counter} busy={pressing === "fps"} disabled={pressing !== null && pressing !== "fps"}
            onPress={() => void press("fps")} />
        )}
        <ListRow first={!optiscaler} label={t("up.play.compare")} chevron onPress={onCompare} />
        {optiscaler && (
          <ListRow label={t("up.play.menu")} detail={t("up.play.menu.detail")} busy={pressing === "menu"}
            disabled={pressing !== null && pressing !== "menu"} onPress={() => void press("menu")} />
        )}
        {fg && live.canPause && (
          <ListRow label={t("up.play.pause")} on={live.generating === false} busy={pressing === "fg"}
            disabled={pressing !== null && pressing !== "fg"} onPress={() => void press("fg")} />
        )}
      </ListCard>
      {failed && <Note tone="warn">{t("up.live.failed")}</Note>}
    </>
  );
};
