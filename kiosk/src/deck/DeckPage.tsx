import { FC, PointerEvent, ReactNode, useEffect, useRef, useState } from "react";

import type { FanPreset } from "../../../src/api";
import { useI18n } from "../../../src/i18n";
import { usePotencia } from "../../../src/tdp/potenciaContext";
import { PotenciaProviderMount } from "../../../src/sections/providerMounts";
import { useFanCurve } from "../../../src/fans/useFanCurve";
import { useCpu } from "../../../src/system/useCpu";
import { useNight } from "../../../src/display/useNight";
import { fanRpm, hottest } from "../now/metrics";
import type { Live } from "../now/live";
import { faderRange, headline, levelCaption, pushSample, sparkPath, valueAt } from "./deckMath";

const HISTORY = 90;
const FAN_CHOICES: FanPreset[] = ["auto", "silent", "balanced", "performance"];

const Fader: FC<{
  value: number | null;
  min: number;
  max: number;
  label: string;
  caption: string;
  locked: boolean;
  onCommit: (value: number) => void;
}> = ({ value, min, max, label, caption, locked, onCommit }) => {
  const [dragging, setDragging] = useState<number | null>(null);
  const shown = dragging ?? value;
  const fill = shown == null || max <= min ? 0 : (shown - min) / (max - min);
  const at = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return valueAt(box.bottom - event.clientY, box.height, min, max);
  };
  return (
    <div
      className={`d-fader${locked ? " is-locked" : ""}${dragging != null ? " is-active" : ""}${fill > 0.78 ? " is-full" : ""}`}
      onPointerDown={(event) => {
        if (locked || value == null) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(at(event));
      }}
      onPointerMove={(event) => {
        if (dragging != null) setDragging(at(event));
      }}
      onPointerUp={() => {
        if (dragging != null && dragging !== value) onCommit(dragging);
        setDragging(null);
      }}
      onPointerCancel={() => setDragging(null)}
    >
      <div className="d-fader-fill" style={{ height: `${8 + fill * 92}%` }} />
      <div className="d-fader-top">
        <span>{label}</span>
        <b>{shown ?? "—"}</b>
      </div>
      <div className="d-fader-caption">{caption}</div>
    </div>
  );
};

const Toggle: FC<{ on: boolean; label: string; detail?: string; icon: ReactNode; onPress: () => void }> = ({
  on, label, detail, icon, onPress,
}) => (
  <button type="button" className={`d-toggle${on ? " is-on" : ""}`} onClick={onPress} aria-pressed={on}>
    <span className="d-toggle-icon">{icon}</span>
    <span className="d-toggle-text">
      <b>{label}</b>
      {detail && <small>{detail}</small>}
    </span>
  </button>
);

const ICONS = {
  auto: (
    <svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9" /><path d="M12 7v5l3 2" /><path d="M17 3h4v4" /></svg>
  ),
  turbo: <svg viewBox="0 0 24 24"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z" /></svg>,
  night: <svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>,
};

const Deck: FC<{ live: Live }> = ({ live }) => {
  const { t, lang } = useI18n();
  const potencia = usePotencia();
  const fan = useFanCurve();
  const cpu = useCpu();
  const night = useNight();
  const { tdp, power } = potencia;
  const history = useRef<number[]>([]);
  const [, tick] = useState(0);

  const temp = hottest(live.fans);
  const reading = headline(power, temp);
  useEffect(() => {
    history.current = [];
  }, [reading.kind]);
  useEffect(() => {
    if (reading.value == null) return;
    history.current = pushSample(history.current, reading.value, HISTORY);
    tick((n) => n + 1);
  }, [power, live.fans]);

  const spark = sparkPath(history.current, 300, 60);
  const range = faderRange(tdp, power?.on_ac ?? false);
  const levelUnit = tdp?.unit === "level";
  const autoOn = Boolean(power?.auto_tdp);
  const value = tdp?.supported ? Math.round(tdp.watts) : null;
  const rpm = fanRpm(live.fans);
  const stats = [
    { kind: "watts", label: t("kiosk.now.power"), value: power?.watts != null ? `${power.watts.toFixed(1)} W` : null },
    { kind: "temp", label: t("kiosk.now.temp"), value: temp != null ? `${Math.round(temp)} °C` : null },
  ].filter((stat) => stat.kind !== reading.kind && stat.value != null);
  const boost = cpu.state?.boost;
  const fanPresets = new Set(["auto", ...(fan.state?.presets ?? []).map((p) => p.id)]);
  const fanChoices = FAN_CHOICES.filter((id) => fanPresets.has(id));

  return (
    <div className="d-deck">
      <Fader
        value={value}
        min={range.min}
        max={range.max}
        label={autoOn ? t("kiosk.deck.auto") : t(levelUnit ? "kiosk.now.level" : "kiosk.deck.watts")}
        caption={levelUnit ? levelCaption(tdp, value, lang) : value != null ? `${value} W` : ""}
        locked={autoOn || !tdp?.supported || potencia.monitorOnly}
        onCommit={(next) => potencia.onWatts(next)}
      />

      <section className={`d-live${stats.length === 0 ? " is-bare" : ""}`}>
        <div className="d-live-main">
          <b>{reading.value == null ? "—" : reading.kind === "watts" ? reading.value.toFixed(1) : Math.round(reading.value)}</b>
          <span>{reading.kind === "fps" ? "fps" : reading.kind === "watts" ? "W" : "°C"}</span>
        </div>
        <svg className="d-spark" viewBox="0 0 300 60" preserveAspectRatio="none" aria-hidden>
          <defs>
            <linearGradient id="d-spark-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="var(--k-accent)" stopOpacity=".16" />
              <stop offset="1" stopColor="var(--k-accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path className="d-spark-area" d={spark.area} />
          <path className="d-spark-line" d={spark.line} />
        </svg>
        {stats.length > 0 && (
          <dl className="d-live-stats">
            {stats.map((stat) => (
              <div key={stat.kind}><dt>{stat.label}</dt><dd>{stat.value}</dd></div>
            ))}
          </dl>
        )}
      </section>

      {fan.state?.supported && fanChoices.length > 1 && (
        <section className="d-fan">
          <div className="d-fan-head">
            <span className="d-section-label">{t("kiosk.now.fan")}</span>
            {rpm != null && <span className="d-fan-rpm">{rpm.toLocaleString(lang)} rpm</span>}
          </div>
          <div className="d-segment" role="radiogroup">
            {fanChoices.map((id) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={fan.state?.preset === id}
                className={fan.state?.preset === id ? "is-on" : undefined}
                onClick={() => fan.onPreset(id)}
              >
                {t(`fans.preset.${id}`)}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="d-toggles">
        {tdp?.supports_auto_tdp !== false && potencia.autoTdpEnabled && (
          <Toggle
            on={autoOn}
            label={t(levelUnit ? "kiosk.deck.autoLevel" : "kiosk.deck.autoTdp")}
            detail={autoOn ? t(`kiosk.now.auto.${power?.auto.state ?? "holding"}`) : t("kiosk.now.off")}
            icon={ICONS.auto}
            onPress={() => potencia.onAutoTdpToggle(!autoOn)}
          />
        )}
        {boost?.supported && (
          <Toggle
            on={boost.enabled}
            label={t("kiosk.deck.turbo")}
            icon={ICONS.turbo}
            onPress={() => cpu.setBoost(!boost.enabled)}
          />
        )}
        {night.state?.supported && (
          <Toggle
            on={night.state.enabled}
            label={t("kiosk.deck.night")}
            icon={ICONS.night}
            onPress={() => night.update({ enabled: !night.state?.enabled })}
          />
        )}
      </section>
    </div>
  );
};

export const DeckPage: FC<{ live: Live }> = ({ live }) => (
  <PotenciaProviderMount>
    <Deck live={live} />
  </PotenciaProviderMount>
);
