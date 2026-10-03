import { FC, useEffect, useState } from "react";

import { useI18n } from "../../../src/i18n";
import { useRunningGame } from "../../../src/tdp/useRunningGame";
import { batteryReading, formatMinutes } from "../now/metrics";
import { formatPlaying, pacePath } from "./deckMath";
import { artUrl, LiveFrame, useBattery } from "./live";

const PACE_W = 300;
const PACE_H = 24;

function useClock(lang: string): string {
  const read = () => new Date().toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  const [now, setNow] = useState(read);
  useEffect(() => {
    const id = window.setInterval(() => setNow(read()), 10_000);
    return () => window.clearInterval(id);
  }, [lang]);
  return now;
}

/** Art that may not exist: hidden until it loads, gone if it fails. */
const Art: FC<{ src: string | null; className: string }> = ({ src, className }) => {
  const [state, setState] = useState<"loading" | "ok" | "missing">("loading");
  useEffect(() => setState("loading"), [src]);
  if (!src || state === "missing") return null;
  return (
    <img
      className={`${className}${state === "ok" ? " is-on" : ""}`}
      src={src}
      alt=""
      onLoad={() => setState("ok")}
      onError={() => setState("missing")}
    />
  );
};

export const Header: FC<{ frame: LiveFrame; target: number | null; celsius: number | null }> = ({ frame, target, celsius }) => {
  const { t, lang } = useI18n();
  const game = useRunningGame();
  const battery = batteryReading(useBattery());
  const clock = useClock(lang);
  const steamApp = game && /^\d+$/.test(game.appid) ? game.appid : null;
  const playing = formatPlaying(frame.playingS);
  const pace = pacePath(frame.history, target, PACE_W, PACE_H);
  const batteryText = battery.percent == null
    ? null
    : battery.minutesLeft != null
      ? `${battery.percent} % · ${formatMinutes(battery.minutesLeft)}`
      : `${battery.percent} %`;

  return (
    <header className="h-head">
      <Art src={steamApp ? artUrl(steamApp, "hero") : null} className="h-banner" />
      <div className="h-shade" />
      <div className="h-top">
        <span>{clock}</span>
        {batteryText && <span className={battery.mood === "charging" ? "is-charging" : undefined}>{batteryText}</span>}
      </div>
      <div className="h-game">
        <Art src={steamApp ? artUrl(steamApp, "logo") : null} className="h-logo" />
        {game && <div className="h-name">{game.name}</div>}
        {playing && <div className="h-session">{t("kiosk.header.playing", { time: playing })}</div>}
      </div>
      <div className="h-stats">
        {celsius != null && (
          <div className="h-temp">
            <b>{Math.round(celsius)}°</b>
            <small>{t("kiosk.header.temp")}</small>
          </div>
        )}
        {frame.fps != null && (
          <div className="h-fps">
            <b>{Math.round(frame.fps)}</b>
            <small>{target != null ? t("kiosk.header.target", { fps: target }) : "fps"}</small>
          </div>
        )}
      </div>
      {pace.line && (
        <svg className="h-pace" viewBox={`0 0 ${PACE_W} ${PACE_H}`} preserveAspectRatio="none" aria-hidden>
          {pace.targetY != null && <line x1="0" y1={pace.targetY} x2={PACE_W} y2={pace.targetY} />}
          <path d={pace.line} />
        </svg>
      )}
    </header>
  );
};
