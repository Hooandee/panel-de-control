import { FC, useState } from "react";

import { useI18n } from "../../../src/i18n";
import {
  coloresEffects, coloresMaxBrightness, coloresModes, lightsSwatch, Rgb, sameRgb, SWATCHES,
} from "./deckMath";
import { Chips, HBar, Hero, Orb, Orbs } from "./Glass";
import { ICON, LIGHT_MODE_ICON } from "./icons";
import type { ColoresControl } from "./steam";

function useLightsText(colores: ColoresControl): string {
  const { t } = useI18n();
  const state = colores.state;
  if (colores.installed === false) return t("kiosk.lights.install");
  if (!state) return "—";
  if (!state.power) return t("kiosk.lights.off");
  const name = state.mode === "effect" ? t(`kiosk.lights.effect.${state.effect.id}`) : t(`kiosk.lights.mode.${state.mode}`);
  return `${name} · ${Math.round((state.brightness / coloresMaxBrightness(state)) * 100)} %`;
}

export const LightsTile: FC<{ colores: ColoresControl; onPress: () => void }> = ({ colores, onPress }) => {
  const { t } = useI18n();
  const swatch = lightsSwatch(colores.state);
  const summary = useLightsText(colores);
  return (
    <button
      type="button"
      className={`t-tile t-rgb${colores.installed === false ? " is-missing" : ""}`}
      disabled={colores.installed == null}
      onClick={onPress}
    >
      <div className="t-row">
        <span className="t-label">{t("kiosk.lights")}</span>
        <span className="t-sub">{summary}</span>
      </div>
      <div className={`t-strip${swatch ? "" : " is-off"}`} style={swatch ? { background: swatch } : undefined} />
    </button>
  );
};

const InstallColores: FC<{ colores: ColoresControl; onError: (error: unknown) => void }> = ({ colores, onError }) => {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const install = async () => {
    setBusy(true);
    try {
      if (!(await colores.install())) onError(new Error("install_failed"));
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Hero bubble={ICON.rainbow} title={t("kiosk.lights.installTitle")} detail={t("kiosk.lights.installDetail")} />
      <div className="g-note">{t("kiosk.lights.installNote")}</div>
      <button type="button" className="g-cta" disabled={busy} onClick={() => void install()}>
        {busy ? t("kiosk.lights.installing") : t("kiosk.lights.install")}
      </button>
    </>
  );
};

export const LightsDialog: FC<{ colores: ColoresControl; onError: (error: unknown) => void }> = ({ colores, onError }) => {
  const { t } = useI18n();
  const state = colores.state;
  if (colores.installed === false) return <InstallColores colores={colores} onError={onError} />;
  if (!state) return null;

  const max = coloresMaxBrightness(state);
  const modes = coloresModes(state.capabilities);
  const effects = coloresEffects(state.capabilities);
  const run = (write: Promise<void>) => void write.catch(onError);
  const pickMode = (mode: string) => {
    if (!state.power) run(colores.setPower(true));
    run(colores.patch({ mode }, { mode, power: true }));
  };
  const pickColor = (color: Rgb) => run(colores.patch({ color: [color.r, color.g, color.b], mode: "solid" }, { color, mode: "solid" }));
  const pickEffect = (id: string) => {
    const effect = { ...state.effect, id };
    run(colores.patch({ mode: "effect", effect: { id, speed: effect.speed, use_gradient: effect.useGradient } }, { mode: "effect", effect }));
  };
  const setSpeed = (fraction: number) => {
    const speed = Math.round(fraction * 100);
    const effect = { ...state.effect, speed };
    run(colores.patch({ effect: { id: effect.id, speed, use_gradient: effect.useGradient } }, { effect }));
  };
  const setBrightness = (fraction: number) => {
    const brightness = Math.round(fraction * max);
    run(colores.patch({ brightness }, { brightness }));
  };

  const title = !state.power
    ? t("kiosk.lights.off")
    : state.mode === "effect" ? t(`kiosk.lights.effect.${state.effect.id}`) : t(`kiosk.lights.mode.${state.mode}`);
  const swatch = lightsSwatch(state);
  const mode = state.power ? state.mode : null;

  return (
    <>
      <Hero
        bubble={null}
        bubbleStyle={swatch ? { background: swatch } : undefined}
        title={title}
        detail={t("kiosk.lights.detail")}
      />
      <Orbs scroll>
        <Orb on={!state.power} label={t("kiosk.lights.turnOff")} onPress={() => run(colores.setPower(!state.power))}>
          {ICON.power}
        </Orb>
        {modes.map((id) => (
          <Orb key={id} on={mode === id} label={t(`kiosk.lights.mode.${id}`)} onPress={() => pickMode(id)}>
            {LIGHT_MODE_ICON[id]}
          </Orb>
        ))}
      </Orbs>

      {mode === "solid" && (
        <div className="g-colors">
          {SWATCHES.map((color) => (
            <button
              key={`${color.r}-${color.g}-${color.b}`}
              type="button"
              className={sameRgb(color, state.color) ? "is-on" : undefined}
              style={{ background: `rgb(${color.r},${color.g},${color.b})` }}
              onClick={() => pickColor(color)}
            />
          ))}
        </div>
      )}

      {mode === "effect" && (
        <>
          <Chips
            items={effects.map((id) => ({ id, label: t(`kiosk.lights.effect.${id}`) }))}
            selected={state.effect.id}
            onPick={pickEffect}
          />
          <HBar value={state.effect.speed / 100} icon={ICON.speed} label={t("kiosk.lights.speed")} onCommit={setSpeed} />
        </>
      )}

      {mode != null && mode !== "solid" && mode !== "effect" && (
        <div className="g-note">{t(`kiosk.lights.note.${mode === "gradient" ? "gradient" : "auto"}`)}</div>
      )}

      <HBar value={state.power ? state.brightness / max : null} icon={ICON.sun} label={t("kiosk.lights.brightness")} onCommit={setBrightness} />
    </>
  );
};
