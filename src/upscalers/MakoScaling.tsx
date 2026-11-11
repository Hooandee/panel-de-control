import { useEffect, useRef, useState } from "react";
import { LuArrowLeftRight, LuTriangleAlert } from "react-icons/lu";
import { getMakoStatus, installMako, refreshFrameGenEngine, type EngineUpdate, type MakoStatus } from "../api";
import { ContainedSlider } from "../components/ContainedSlider";
import { useI18n } from "../i18n";
import { saveExclusiveMakoProfile } from "./jobRunner";
import { useMakoLeftover } from "./makoLeftover";
import { ActionButton, ListCard, Note, Notice, Row, Spinner } from "./parts";
import { upscalerErrorCode } from "./errorCode";

/** Brings the installed engine up to date when it can; the installed version keeps working when it cannot. */
async function refreshEngine(): Promise<EngineUpdate["state"]> {
  try {
    const update = await refreshFrameGenEngine("mako", false);
    return update.state === "available" ? (await refreshFrameGenEngine("mako", true)).state : update.state;
  } catch {
    return "failed";
  }
}

export function MakoScaling({ appid, liveAppid, isNonSteam, disabled, gameRunning, mixed, onChanged }: {
  appid: string; liveAppid: number; isNonSteam: boolean; disabled: boolean; gameRunning: boolean; mixed: boolean; onChanged?: () => void;
}) {
  const { t } = useI18n();
  const [status, setStatus] = useState<MakoStatus | null>(null);
  const [factor, setFactor] = useState(1.5);
  const [sharpness, setSharpness] = useState(80);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [engineNotice, setEngineNotice] = useState<string | null>(null);
  const alive = useRef(true);
  const accept = (next: MakoStatus) => {
    setStatus(next);
    const profile = next.profiles[appid];
    setFactor(profile?.scaling_factor ?? 1.5);
    setSharpness(Math.round((profile?.scaling_sharpness ?? 0.8) * 100));
    setDirty(false);
  };
  const load = async () => {
    try { const next = await getMakoStatus(appid); if (alive.current) accept(next); }
    catch { if (alive.current) setError(t("up.error.generic")); }
  };
  useEffect(() => {
    alive.current = true;
    void load();
    return () => { alive.current = false; };
  }, [appid]);
  useEffect(() => {
    let mounted = true;
    const refresh = () => { void getMakoStatus(appid).then(next => { if (mounted) setStatus(next); }).catch(() => {}); };
    window.addEventListener("pdc-mako-changed", refresh);
    return () => { mounted = false; window.removeEventListener("pdc-mako-changed", refresh); };
  }, [appid]);
  const profile = status?.profiles[appid];
  const active = !!profile?.scaling_enabled;
  const makoLeftover = useMakoLeftover(appid, liveAppid, !!isNonSteam);
  const leftover = !profile && makoLeftover.leftover;
  const blocked = disabled || gameRunning || busy || !status || !status.supported || leftover || mixed || status.reason === "mako_identity_ambiguous";
  const save = async (enabled: boolean) => {
    if (blocked) return;
    setBusy(true); setError(null); setSaved(false); setEngineNotice(null);
    try {
      if (enabled) {
        if (!status.installed) await installMako();
        const update = await refreshEngine();
        if (alive.current) setEngineNotice(update === "deferred" ? t("up.engine.deferred") : update === "failed" ? t("up.engine.failed") : null);
      }
      await saveExclusiveMakoProfile({ appid, liveAppid, isNonSteam }, {
        scaling_enabled: enabled,
        scaling_factor: factor, scaling_sharpness: sharpness / 100,
      });
      onChanged?.();
      await load();
      if (alive.current) setSaved(true);
    } catch (caught) {
      if (alive.current) {
        const key = `up.error.${upscalerErrorCode(caught)}`;
        setError(t(key) === key ? t("up.error.generic") : t(key));
      }
    } finally { if (alive.current) setBusy(false); }
  };
  return <>
    <ListCard>
      <ContainedSlider label={t("up.mako.scaling.factor")} value={factor} min={1} max={2} step={0.05}
        showValue disabled={blocked} bottomSeparator="none" onChange={value => { if (!blocked) { setFactor(Math.round(Math.max(1, Math.min(2, value)) * 100) / 100); setDirty(true); setSaved(false); } }} />
      <ContainedSlider label={t("up.image.sharpness")} value={sharpness} min={0} max={100} step={1}
        showValue disabled={blocked} bottomSeparator="none" onChange={value => { if (!blocked) { setSharpness(Math.round(Math.max(0, Math.min(100, value)))); setDirty(true); setSaved(false); } }} />
    </ListCard>
    <Note>{t("up.mako.scaling.hint")}</Note>
    {mixed && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.mako.scaling.mixed")}</Notice>}
    {status && !status.supported && <Note>{t("up.mako.unsupported")}</Note>}
    {leftover && <>
      <Notice icon={<LuArrowLeftRight size={16} />}>{t("up.mako.leftover")}</Notice>
      <Row><ActionButton label={t("up.mako.leftover.clear")} disabled={disabled || gameRunning} onPress={() => { setError(null); void makoLeftover.clear().catch(() => { if (alive.current) setError(t("up.lsfg.launchFailed")); }); }} /></Row>
    </>}
    {status?.reason === "mako_identity_ambiguous" && <Note>{t("up.mako.identity")}</Note>}
    {gameRunning && <Note>{t("up.error.running")}</Note>}
    {busy && <Note><Spinner size={12} /> {t("up.activating")}</Note>}
    <Row>
      {dirty && <ActionButton label={t("up.discard")} disabled={busy} onPress={() => { if (status) accept(status); }} />}
      {(!active || dirty) && <ActionButton primary label={t(active ? "up.save" : "up.activate", { name: "Mako" })} disabled={blocked} busy={busy} onPress={() => void save(true)} />}
      {active && <ActionButton label={t("up.deactivate", { name: "Mako" })} disabled={blocked} onPress={() => void save(false)} />}
    </Row>
    {engineNotice && <Note>{engineNotice}</Note>}
    {saved && <Note>{t("up.image.saved")}</Note>}
    {error && <><Note>{error}</Note>{!status && <ActionButton label={t("up.image.retry")} onPress={() => void load()} />}</>}
  </>;
}
