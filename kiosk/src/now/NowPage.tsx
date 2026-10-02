import { CSSProperties, FC, useEffect, useState } from "react";

import { useI18n } from "../../../src/i18n";
import { artUrl, Live, RunningGame } from "./live";
import {
  batteryReading,
  fanRpm,
  formatMinutes,
  gpuFraction,
  hottest,
  powerReading,
  tempFraction,
} from "./metrics";

const RINGS = [
  { r: 65, color: "var(--k-accent)" },
  { r: 52, color: "var(--k-ok)" },
  { r: 39, color: "var(--k-hot)" },
] as const;

function useNow(everyMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs]);
  return now;
}

const Ring: FC<{ r: number; color: string; fraction: number }> = ({ r, color, fraction }) => {
  const length = 2 * Math.PI * r;
  return (
    <>
      <circle className="k-ring-track" cx="75" cy="75" r={r} stroke={color} />
      <circle
        className="k-ring-bar"
        cx="75"
        cy="75"
        r={r}
        stroke={color}
        transform="rotate(-90 75 75)"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - Math.max(0.002, fraction))}
      />
    </>
  );
};

const useImage = (src: string | null) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(false);
    if (!src) return;
    const image = new Image();
    image.onload = () => setReady(true);
    image.src = src;
    return () => {
      image.onload = null;
    };
  }, [src]);
  return ready;
};

const Hero: FC<{ game: RunningGame | null; fps: number | null }> = ({ game, fps }) => {
  const { t, lang } = useI18n();
  const now = useNow(game ? 30_000 : 1000);
  const hero = game ? artUrl(game.appid, "hero") : null;
  const logo = game ? artUrl(game.appid, "logo") : null;
  const heroReady = useImage(hero);
  const logoReady = useImage(logo);

  if (!game) {
    return (
      <article className="k-card k-hero is-idle k-reveal" style={{ "--i": 0 } as CSSProperties}>
        <div className="k-standby-time">
          {now.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}
        </div>
        <div className="k-standby-date">
          {now.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" })}
        </div>
      </article>
    );
  }

  const minutes = Math.max(0, Math.floor((now.getTime() - game.since) / 60_000));
  return (
    <article className="k-card k-hero k-reveal" style={{ "--i": 0 } as CSSProperties}>
      <div className={`k-hero-art${heroReady ? " is-ready" : ""}`} style={{ backgroundImage: hero ? `url(${hero})` : undefined }} />
      <div className="k-hero-shade" />
      {fps != null && (
        <div className="k-fps">
          <b>{Math.round(fps)}</b>
          <span>FPS</span>
        </div>
      )}
      <div className="k-hero-foot">
        {logoReady && logo ? (
          <img className="k-hero-logo" src={logo} alt={game.name ?? ""} />
        ) : (
          <div className="k-hero-title">{game.name ?? t("kiosk.now.game")}</div>
        )}
        <div className="k-hero-meta">
          <i className="k-live" />
          {minutes < 1 ? t("kiosk.now.started") : t("kiosk.now.playing", { time: formatMinutes(minutes) })}
        </div>
      </div>
    </article>
  );
};

export const NowPage: FC<{ live: Live; game: RunningGame | null }> = ({ live, game }) => {
  const { t } = useI18n();
  const power = powerReading(live.tdp, live.power);
  const temp = hottest(live.fans);
  const gpu = live.power?.gpu_busy ?? null;
  const battery = batteryReading(live.battery);
  const rpm = fanRpm(live.fans);
  const fps = live.power?.auto?.fps ?? null;
  const ownProfile = Boolean(live.tdp?.has_game_profile && !live.tdp?.follows_global);
  const batteryLabel =
    battery.mood === "charging" ? t("kiosk.now.charging")
    : battery.mood === "full" ? t("kiosk.now.full")
    : battery.minutesLeft != null ? t("kiosk.now.remaining", { time: formatMinutes(battery.minutesLeft) })
    : t("kiosk.now.battery");

  return (
    <div className="k-now">
      <Hero game={game} fps={fps} />

      <article className="k-card k-rings k-reveal" style={{ "--i": 1 } as CSSProperties}>
        <div className="k-rings-dial">
          <svg viewBox="0 0 150 150" aria-hidden>
            <Ring {...RINGS[0]} fraction={power.fraction} />
            <Ring {...RINGS[1]} fraction={gpuFraction(live.power)} />
            <Ring {...RINGS[2]} fraction={tempFraction(temp)} />
          </svg>
          <div className="k-rings-centre">
            {power.unit === "level" ? (
              <>
                <span className="k-rings-caption">{t("kiosk.now.level")}</span>
                <b>{power.value ?? "—"}</b>
              </>
            ) : (
              <>
                <b>{power.value != null ? power.value.toFixed(1) : "—"}</b>
                <span className="k-rings-caption">W</span>
              </>
            )}
          </div>
        </div>
        <div className="k-legend">
          <span style={{ "--c": "var(--k-accent)" } as CSSProperties}>
            <b>{power.watts != null ? `${power.watts.toFixed(1)} W` : "—"}</b>
            {t("kiosk.now.power")}
          </span>
          <span style={{ "--c": "var(--k-ok)" } as CSSProperties}>
            <b>{gpu != null ? `${Math.round(gpu)}%` : "—"}</b>
            GPU
          </span>
          <span style={{ "--c": "var(--k-hot)" } as CSSProperties}>
            <b>{temp != null ? `${Math.round(temp)}°` : "—"}</b>
            {t("kiosk.now.temp")}
          </span>
        </div>
      </article>

      <article className={`k-card k-battery is-${battery.mood} k-reveal`} style={{ "--i": 2 } as CSSProperties}>
        <div className="k-battery-top">
          <span className="k-rings-caption">{t("kiosk.now.battery")}</span>
          {battery.mood === "charging" && <span className="k-bolt" aria-hidden>⚡︎</span>}
        </div>
        <div className="k-battery-value">
          <b>{battery.percent ?? "—"}</b>
          {battery.percent != null && <span>%</span>}
        </div>
        <div className="k-capsule">
          <div style={{ width: `${battery.percent ?? 0}%` }} />
        </div>
        <div className="k-battery-label">{batteryLabel}</div>
      </article>

      <div className="k-strip">
        <div className="k-card k-tile k-reveal" style={{ "--i": 3 } as CSSProperties}>
          <span className="k-rings-caption">{t("kiosk.now.fan")}</span>
          <div className="k-tile-value">
            <svg className="k-fan" viewBox="0 0 24 24" aria-hidden style={{ animationDuration: rpm ? `${Math.max(0.3, 2400 / rpm)}s` : "0s" }}>
              <circle cx="12" cy="12" r="1.6" />
              <path d="M12 10.4c-.4-3 .3-6.4 3-6.9 2.4-.4 3.4 2.6 1.2 4.3-1.2.9-2.7 1.7-4.2 2.6zM13.6 12c3-.4 6.4.3 6.9 3 .4 2.4-2.6 3.4-4.3 1.2-.9-1.2-1.7-2.7-2.6-4.2zM12 13.6c.4 3-.3 6.4-3 6.9-2.4.4-3.4-2.6-1.2-4.3 1.2-.9 2.7-1.7 4.2-2.6zM10.4 12c-3 .4-6.4-.3-6.9-3-.4-2.4 2.6-3.4 4.3-1.2.9 1.2 1.7 2.7 2.6 4.2z" />
            </svg>
            <b>{rpm != null ? rpm.toLocaleString() : "—"}</b>
            {rpm != null && <small>rpm</small>}
          </div>
        </div>
        <div className="k-card k-tile k-reveal" style={{ "--i": 4 } as CSSProperties}>
          <span className="k-rings-caption">{t("kiosk.now.auto")}</span>
          <div className="k-tile-value">
            <i className={`k-dot${live.power?.auto_tdp ? " is-on" : ""}`} />
            <b className="k-tile-word">{live.power?.auto_tdp ? t(`kiosk.now.auto.${live.power.auto.state}`) : t("kiosk.now.off")}</b>
          </div>
        </div>
        <div className="k-card k-tile k-reveal" style={{ "--i": 5 } as CSSProperties}>
          <span className="k-rings-caption">{t("kiosk.now.profile")}</span>
          <div className="k-tile-value">
            <b className="k-tile-word">{t(ownProfile ? "kiosk.now.profile.game" : "kiosk.now.profile.global")}</b>
          </div>
        </div>
      </div>
    </div>
  );
};
