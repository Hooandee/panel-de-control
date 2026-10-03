import { FC, ReactNode, useState } from "react";

import { setKioskScreenOff, type FanPreset } from "../../../src/api";
import { useI18n } from "../../../src/i18n";
import { usePotencia } from "../../../src/tdp/potenciaContext";
import { resolveAutoView } from "../../../src/tdp/autoView";
import { resolveLivePresets } from "../../../src/tdp/livePresets";
import { presetTitle } from "../../../src/tdp/powerPresets";
import { presetIconNode } from "../../../src/tdp/powerPresetIcons";
import { isLevelUnit } from "../../../src/tdp/unit";
import { useFanCurve } from "../../../src/fans/useFanCurve";
import { useCpu } from "../../../src/system/useCpu";
import { toaster } from "../shims/deckyApi";
import { fanRpm, hottest } from "../now/metrics";
import { fpsChoices, levelCaption, refreshChoices, stepRange } from "./deckMath";
import { GlassDialog, Hero, Orb, Orbs, Steps, usePresence, VFader } from "./Glass";
import { FAN_PRESET_ICON, FanIcon, ICON } from "./icons";
import { Header } from "./Header";
import { LightsDialog, LightsTile } from "./Lights";
import { useFans, useLiveFrame, useVitals } from "./live";
import { SteamActionError, steamCall, useColores, useRefreshRate, useSteamScalar } from "./steam";

type DialogId = "perf" | "fps" | "fan" | "hz" | "lights";

const FAN_CHOICES: FanPreset[] = ["auto", "silent", "balanced", "performance"];
const PICK_CLOSE_MS = 380;

const LiveFps: FC = () => {
  const { fps } = useLiveFrame();
  return <>{fps == null ? "— fps" : `${Math.round(fps)} fps`}</>;
};

const Vitals: FC = () => {
  const { t, lang } = useI18n();
  const vitals = useVitals();
  const number = (value: number, digits: number) =>
    value.toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const items = [
    { id: "cpu", label: "CPU", unit: "GHz", value: vitals?.cpu_mhz != null ? number(vitals.cpu_mhz / 1000, 2) : null },
    { id: "gpu", label: "GPU", unit: "MHz", value: vitals?.gpu_mhz != null ? String(vitals.gpu_mhz) : null },
    {
      id: "pwr",
      label: t(vitals?.charging ? "kiosk.vitals.charging" : "kiosk.vitals.power"),
      unit: "W",
      value: vitals?.watts != null ? number(vitals.watts, 1) : null,
    },
    { id: "ram", label: "RAM", unit: "GB", value: vitals?.ram_used_gb != null ? number(vitals.ram_used_gb, 1) : null },
  ].filter((item) => item.value != null);
  if (items.length === 0) return null;
  return (
    <dl className="t-vitals">
      {items.map((item) => (
        <div key={item.id}>
          <dt>{item.label}</dt>
          <dd>
            {item.value}
            <small>{item.unit}</small>
          </dd>
        </div>
      ))}
    </dl>
  );
};

const Tile: FC<{
  area: string;
  small?: boolean;
  on?: boolean;
  disabled?: boolean;
  onPress?: () => void;
  children: ReactNode;
}> = ({ area, small, on, disabled, onPress, children }) => (
  <button
    type="button"
    className={`t-tile t-${area}${small ? " is-small" : ""}${on ? " is-on" : ""}`}
    disabled={disabled || !onPress}
    onClick={onPress}
  >
    {children}
  </button>
);

export const Deck: FC<{ onScreenOff: () => void }> = ({ onScreenOff }) => {
  const { t, lang } = useI18n();
  const potencia = usePotencia();
  const fan = useFanCurve();
  const cpu = useCpu();
  const fans = useFans();
  const brightness = useSteamScalar("brightness");
  const volume = useSteamScalar("volume");
  const refresh = useRefreshRate();
  const colores = useColores();
  const [open, setOpen] = useState<DialogId | null>(null);
  const presence = usePresence(open);

  const { tdp, power, scope, game } = potencia;
  const close = () => setOpen(null);
  const pickAndClose = (action: () => unknown) => {
    void action();
    window.setTimeout(close, PICK_CLOSE_MS);
  };
  const fail = (error: unknown) => {
    const unsupported = error instanceof SteamActionError && error.message === "unsupported";
    toaster.toast({ title: t(unsupported ? "kiosk.unsupported" : "kiosk.failed") });
  };
  const steam = (action: string) => () => void steamCall(action).catch(fail);

  const perfReady = Boolean(tdp?.supported) && !potencia.monitorOnly;
  const levels = isLevelUnit(tdp?.unit);
  const range = stepRange(tdp, tdp?.on_ac ?? false);
  const autoView = tdp ? resolveAutoView(tdp, power, scope, Boolean(game)) : null;
  const autoOn = Boolean(autoView?.config.enabled);
  const autoReady = perfReady && potencia.autoTdpEnabled && tdp?.supports_auto_tdp !== false;
  const target = autoReady && autoOn ? autoView?.config.target_fps ?? null : null;
  const value = tdp ? Math.round(scope === "global" ? tdp.global_watts : tdp.watts) : null;
  const shownLevel = autoOn && power?.auto?.setpoint != null ? Math.round(power.auto.setpoint) : value;
  const presets = tdp ? resolveLivePresets(tdp, potencia.presets, scope, t).visible : [];
  const activePreset = presets.find((item) => item.active);
  const perfName = autoOn
    ? t("kiosk.perf.auto")
    : activePreset ? presetTitle(activePreset, t) : t("kiosk.perf.custom");
  const perfDetail = levels ? levelCaption(tdp, shownLevel, lang) : "";
  const unitText = (n: number | null) => (n == null ? "—" : String(n));
  const fill = shownLevel == null || range.max <= range.min ? 0 : (shownLevel - range.min) / (range.max - range.min);
  const lit = shownLevel == null ? 0 : Math.max(1, Math.round(fill * 10));

  const rpm = fanRpm(fans);
  const temp = hottest(fans);
  const fanPresets = new Set(["auto", ...(fan.state?.presets ?? []).map((p) => p.id)]);
  const fanChoices = FAN_CHOICES.filter((id) => fanPresets.has(id));
  const fanReady = Boolean(fan.state?.supported) && fanChoices.length > 1;

  const hzChoices = refresh.range?.settable === false ? [] : refreshChoices(refresh.range);
  const boost = cpu.state?.boost;

  return (
    <>
      <Header target={target} celsius={temp} />

      <div className="t-grid">
        <Tile area="perf" disabled={!perfReady} onPress={() => setOpen("perf")}>
          <div>
            <div className="t-level">
              <b>{unitText(shownLevel)}</b>
              <span>{levels ? `/ ${range.max}` : "W"}</span>
            </div>
            <div className="t-perf-name">{perfReady ? perfName : t("kiosk.unavailable")}</div>
          </div>
          <Vitals />
          <div className="t-mini">
            {Array.from({ length: 10 }, (_, i) => <i key={i} className={i < lit ? "is-on" : undefined} />)}
          </div>
        </Tile>

        <Tile area="fps" small disabled={!autoReady} onPress={() => setOpen("fps")}>
          <span className="t-big">{target ?? "∞"}</span>
          <span className="t-label">{target != null ? t("kiosk.fps.target") : t("kiosk.fps.free")}</span>
        </Tile>

        <Tile area="fan" small onPress={fanReady ? () => setOpen("fan") : undefined}>
          <span className="t-icon"><FanIcon spinning={rpm != null && rpm > 0} /></span>
          <span className="t-label">{rpm == null ? t("kiosk.fan") : rpm > 0 ? `${rpm.toLocaleString(lang)} rpm` : t("kiosk.fan.stopped")}</span>
        </Tile>

        <VFader className="t-bri" value={brightness.value} icon={ICON.sun} label={t("kiosk.brightness")} onChange={brightness.write} onCommit={brightness.commit} />
        <VFader
          className="t-vol"
          value={volume.value}
          icon={volume.value === 0 ? ICON.muted : ICON.speaker}
          label={t("kiosk.volume")}
          onChange={volume.write}
          onCommit={volume.commit}
        />

        <LightsTile colores={colores} onPress={() => setOpen("lights")} />

        <Tile area="hz" small onPress={hzChoices.length > 1 ? () => setOpen("hz") : undefined}>
          <span className="t-big">{refresh.range?.current ?? "—"}</span>
          <span className="t-label">Hz</span>
        </Tile>

        <Tile area="turbo" small on={boost?.enabled} onPress={boost?.supported ? () => cpu.setBoost(!boost.enabled) : undefined}>
          <span className="t-icon">{ICON.bolt}</span>
          <span className="t-label">{t("kiosk.turbo")}</span>
        </Tile>
        <Tile area="shot" small onPress={steam("screenshot")}>
          <span className="t-icon">{ICON.camera}</span>
          <span className="t-label">{t("kiosk.screenshot")}</span>
        </Tile>
        <Tile area="kbd" small onPress={steam("keyboard")}>
          <span className="t-icon">{ICON.keyboard}</span>
          <span className="t-label">{t("kiosk.keyboard")}</span>
        </Tile>
        <Tile area="qam" small onPress={steam("quick_access")}>
          <span className="t-icon">{ICON.dots}</span>
          <span className="t-label">Steam</span>
        </Tile>
        <Tile area="off" small onPress={onScreenOff}>
          <span className="t-icon">{ICON.screenOff}</span>
          <span className="t-label">{t("kiosk.screenOff")}</span>
        </Tile>
      </div>

      {presence.shown && (
        <GlassDialog visible={presence.visible} onClose={close}>
          {presence.shown === "perf" && tdp && (
            <>
              <Hero
                bubble={<b className="g-bubble-num">{unitText(shownLevel)}</b>}
                title={perfName}
                detail={autoOn ? t("kiosk.perf.autoNote") : perfDetail || (levels ? null : `${value} W`)}
              />
              {presets.length > 0 && (
                <Orbs>
                  {presets.map((item) => (
                    <Orb key={item.id} on={item.active && !autoOn} disabled={autoOn} label={presetTitle(item, t)} onPress={() => potencia.onApplyPreset(item)}>
                      {presetIconNode(item.icon, 28)}
                    </Orb>
                  ))}
                </Orbs>
              )}
              <Steps value={shownLevel ?? range.min} min={range.min} max={range.max} disabled={autoOn} onCommit={potencia.onWatts} />
            </>
          )}

          {presence.shown === "fps" && (
            <>
              <Hero
                bubble={ICON.target}
                title={<LiveFps />}
                detail={t(autoOn ? "kiosk.fps.onNote" : "kiosk.fps.offNote")}
              />
              <Orbs>
                {fpsChoices(tdp?.auto_target_max_fps).map((fps) => (
                  <Orb
                    key={fps}
                    on={autoOn && target === fps}
                    label="fps"
                    onPress={() => pickAndClose(() => {
                      potencia.onAutoTargetFps(fps);
                      if (!autoOn) potencia.onAutoTdpToggle(true);
                    })}
                  >
                    {fps}
                  </Orb>
                ))}
                <Orb on={!autoOn} label={t("kiosk.fps.free")} onPress={() => pickAndClose(() => autoOn && potencia.onAutoTdpToggle(false))}>
                  {ICON.infinity}
                </Orb>
              </Orbs>
            </>
          )}

          {presence.shown === "fan" && fan.state && (
            <>
              <Hero
                bubble={<FanIcon spinning={rpm != null && rpm > 0} />}
                title={rpm == null ? t("kiosk.fan") : `${rpm.toLocaleString(lang)} rpm`}
                detail={temp != null ? `${Math.round(temp)} °C` : undefined}
              />
              <Orbs>
                {fanChoices.map((id) => (
                  <Orb key={id} on={fan.state?.preset === id} label={t(`fans.preset.${id}`)} onPress={() => pickAndClose(() => fan.onPreset(id))}>
                    {FAN_PRESET_ICON[id]}
                  </Orb>
                ))}
              </Orbs>
            </>
          )}

          {presence.shown === "hz" && (
            <>
              <Hero bubble={ICON.display} title={`${refresh.range?.current ?? "—"} Hz`} detail={t("kiosk.hz.detail")} />
              <Orbs>
                {hzChoices.map((hz, index) => (
                  <Orb
                    key={hz}
                    on={refresh.range?.current === hz}
                    label={index === 0 ? t("kiosk.hz.saver") : index === hzChoices.length - 1 ? t("kiosk.hz.max") : "Hz"}
                    onPress={() => pickAndClose(() => refresh.set(hz).catch(fail))}
                  >
                    {hz}
                  </Orb>
                ))}
              </Orbs>
            </>
          )}

          {presence.shown === "lights" && <LightsDialog colores={colores} onError={fail} />}
        </GlassDialog>
      )}
    </>
  );
};

/** Turns the bottom panel's backlight off and shows a black catcher that wakes it on touch. */
export function useScreenOff(onFail: () => void): { off: boolean; sleep: () => void; wake: () => void } {
  const [off, setOff] = useState(false);
  const apply = (next: boolean) =>
    setKioskScreenOff(next)
      .then((state) => {
        const isOff = Boolean(state.screen_off);
        setOff(isOff);
        if (isOff !== next) onFail();
      })
      .catch(() => {
        setOff(false);
        onFail();
      });
  return { off, sleep: () => void apply(true), wake: () => void apply(false) };
}
