import { useEffect, useRef, useState, type FC, type ReactNode } from "react";
import { GiPlasticDuck, GiSharkFin } from "react-icons/gi";
import { LuArrowLeftRight, LuLayers, LuSparkles, LuTriangleAlert } from "react-icons/lu";

import {
  refreshFrameGenEngine, adoptForeignLsfg, getLsfgStatus, installLsfg, restoreForeignLsfg, setLsfgGame, type LsfgProfile, type LsfgStatus,
  dismissMakoNotice, getMakoStatus, installMako, type MakoProfile, type MakoStatus,
} from "../api";
import { ExperimentalBadge } from "../components/ExperimentalBadge";
import { NoticeCard } from "../components/NoticeCard";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { readLosslessBranch, switchLosslessBranch, type LosslessBranchState } from "./losslessBranch";
import { fgOffer } from "./model";
import { ActionButton, Label, ListCard, ListRow, Note, Notice, PickerButton, Row } from "./parts";
import { FLOW_MODES, FLOW_PRESETS, FlowScale, flowMode, type FlowMode } from "./FlowScale";
import type { FgRoute } from "./types";

import { applyManagedLaunch } from "./managedLaunch";
import { useMakoLeftover } from "./makoLeftover";
import { saveMakoProfile } from "./makoProfile";
import { transitionFrameGen, type FrameGenStep } from "./frameGenTransition";
import { upscalerErrorCode } from "./errorCode";
import { MakoControls } from "./MakoControls";

type Pick = "off" | FgRoute | "lsfg" | "mako" | "mako5";
const MAKO_NAME = { mako: "Mako 4 Lossless", mako5: "Mako 5" } as const;
const MULTIPLIERS = [2, 3, 4, 5, 6] as const;

function showFrameGenIcon(element: HTMLSpanElement | null) {
  element?.querySelector("svg")?.style.setProperty("display", "inline-block", "important");
}

/** Frame generation where Panel de Control adds something: the game's own on another GPU, OptiScaler's, or Lossless Scaling. */
export const FrameGenRow: FC<{
  appid: string;
  liveAppid: number;
  isNonSteam: boolean;
  gameRunning: boolean;
  duo?: boolean;
  routes: Partial<Record<FgRoute, unknown>>;
  recommendedRoutes?: Partial<Record<FgRoute, unknown>>;
  inputs: Record<string, unknown>;
  optiscaler: { fg: "on" | "off"; route: FgRoute };
  installedRoute: FgRoute | null;
  gpu: string;
  renderAdvanced?: (restore: ReactNode) => ReactNode;
  onOptiscaler: (fg: "on" | "off", route: FgRoute | null) => void;
  onApplyOptiscaler?: (fg: "on" | "off", route: FgRoute | null) => Promise<void>;
  disabled?: boolean;
  optiscalerDisabled?: boolean;
  anrSettings?: { setting: string; value: string }[];
}> = ({ anrSettings = [], appid, liveAppid, isNonSteam, gameRunning, routes, recommendedRoutes, inputs, optiscaler, installedRoute, gpu, onOptiscaler, onApplyOptiscaler, disabled = false, optiscalerDisabled = false, renderAdvanced, duo = false }) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<LsfgStatus | null>(null);
  const [mako, setMako] = useState<MakoStatus | null>(null);
  const [branch, setBranch] = useState<LosslessBranchState | null>(null);
  const branchAbort = useRef<AbortController | null>(null);
  const [selection, setSelection] = useState<Pick | null>(null);
  const [busy, setBusy] = useState(false);
  const [enginePhase, setEnginePhase] = useState<"checking" | "updating" | null>(null);
  const [activating, setActivating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setSelection(null);
    setStatus(null);
    setMako(null);
    getLsfgStatus().then((next) => { if (alive) setStatus(next); }).catch(() => {});
    const reload = () => { void getMakoStatus(appid).then((next) => { if (alive) setMako(next); }).catch(() => {}); };
    reload();
    window.addEventListener("pdc-mako-changed", reload);
    return () => { alive = false; window.removeEventListener("pdc-mako-changed", reload); };
  }, [appid]);

  const makoLeftover = useMakoLeftover(appid, liveAppid, !!isNonSteam);
  const profile = status?.profiles[appid] ?? null;
  const storedMako = mako?.profiles[appid] ?? null;
  const makoProfile = storedMako?.enabled === false ? null : storedMako;
  const lossless = !!status && status.lossless;
  const offer = fgOffer(routes, inputs, gpu, lossless || !!profile, installedRoute);
  const gameInput = (routes.game as { input?: string } | undefined)?.input;
  const dlssBridge = !offer.own && (gameInput === "dlssg" || gameInput === "nukems");
  const makoPick = makoProfile ? (makoProfile.engine === 5 ? "mako5" : "mako") : null;
  const current: Pick = selection ?? (makoPick ?? (profile ? "lsfg" : optiscaler.fg === "on" && offer.options.includes(optiscaler.route) ? optiscaler.route : "off"));
  const isMako = current === "mako" || current === "mako5";
  const makoEngine = current === "mako5" ? 5 : 4;
  const blocked = busy || disabled || enginePhase !== null;

  useEffect(() => {
    if (current !== "lsfg") return;
    const abort = new AbortController();
    branchAbort.current = abort;
    void readLosslessBranch(1500, abort.signal).then((next) => { if (!abort.signal.aborted) setBranch(next); }).catch(() => {});
    return () => { abort.abort(); };
  }, [current]);

  useEffect(() => {
    if (current !== "lsfg" || status?.dll) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      const next = await getLsfgStatus().catch(() => null);
      if (!alive) return;
      if (next) setStatus(next);
      timer = setTimeout(refresh, 3000);
    };
    timer = setTimeout(refresh, 3000);
    return () => { alive = false; clearTimeout(timer); };
  }, [current, !!status?.dll]);

  useEffect(() => {
    if (current !== "mako" || mako?.dll) return;
    let alive = true;
    const timer = setInterval(() => { void getMakoStatus(appid).then((next) => { if (alive) setMako(next); }).catch(() => {}); }, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [current, !!mako?.dll]);

  useEffect(() => {
    if (current !== "mako" && current !== "mako5" && current !== "lsfg") { setEnginePhase(null); return; }
    const engine = current;
    const loaded = engine === "lsfg" ? status !== null : mako !== null;
    if (!loaded || (engine === "lsfg" && status?.foreign) || (engine !== "lsfg" && !mako?.supported)) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      setEnginePhase("checking");
      try {
        let result = await refreshFrameGenEngine(engine, false);
        if (!alive) return;
        const installed = engine === "mako" ? mako?.installed : engine === "mako5" ? mako?.v5?.installed : status?.installed;
        if (result.state === "available" && installed) {
          setEnginePhase("updating");
          result = await refreshFrameGenEngine(engine, true);
          if (!alive) return;
        }
        if (result.state === "updated") {
          if (engine !== "lsfg") { const next = await getMakoStatus(appid); if (alive) setMako(next); }
          else { const next = await getLsfgStatus(); if (alive) setStatus(next); }
        }
        if (!alive) return;
        setMessage(result.state === "deferred" ? t("up.engine.deferred") : result.state === "failed" ? t("up.engine.failed") : null);
        if (result.state === "deferred") timer = setTimeout(refresh, 30000);
      } catch {
        if (alive) setMessage(t("up.engine.failed"));
      } finally {
        if (alive) setEnginePhase(null);
      }
    };
    void refresh();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [current, appid, mako !== null, status !== null, mako?.installed, mako?.v5?.installed, status?.installed]);

  const saveLsfg = async (next: Partial<LsfgProfile> | null) => {
    const result = await setLsfgGame(appid, next);
    let pending = false;
    try {
      const applied = await applyManagedLaunch(appid, liveAppid, "lsfg", { env: result.env }, { isNonSteam, requireComplete: next !== null });
      pending = !!applied.pending;
      if (!applied.ok) throw new Error("launch_failed");
      if (applied.preserved.env.length || applied.preserved.wrappers.length) setMessage(t("up.launch.preserved"));
      else if (gameRunning && next) setMessage(t("up.lsfg.restart"));
    } catch (error) {
      if (!pending || next === null) await setLsfgGame(appid, profile);
      throw error;
    }
  };

  const saveMako = async (next: Partial<MakoProfile> | null, reclaim = false) => {
    const patch = next ? {
      enabled: true, engine: next.engine ?? 4, mode: next.mode, multiplier: next.multiplier, target_fps: next.target_fps,
      max_multiplier: next.max_multiplier, flow: next.flow, performance: next.performance,
      ...(next.fg_mode ? { fg_mode: next.fg_mode } : {}), ...(next.flow_scale !== undefined ? { flow_scale: next.flow_scale } : {}),
    } : { enabled: false };
    await saveMakoProfile(appid, liveAppid, patch, isNonSteam, reclaim);
    if (gameRunning) setMessage(t("up.mako.restart"));
  };

  // Puts back exactly what was stored, engine and spatial scaling included, not a fresh frame generation profile.
  const restoreMako = async () => { await saveMakoProfile(appid, liveAppid, storedMako, isNonSteam); };

  const run = async (work: () => Promise<void>, activate = false) => {
    setBusy(true);
    setActivating(activate);
    setMessage(null);
    try {
      await work();
    } catch (error) {
      const code = upscalerErrorCode(error);
      setMessage(t(code === "mako_identity_ambiguous" ? "up.mako.identity" : code === "mako_foreign" ? "up.mako.foreignProfile" : code === "launch_failed" ? "up.lsfg.launchFailed" : ["mako_dll_missing", "mako_dll_incompatible"].includes(code) ? "up.mako.requirement" : "up.error.generic"));
    } finally {
      await Promise.allSettled([getLsfgStatus().then(setStatus), getMakoStatus(appid).then(setMako)]);
      setBusy(false);
      setActivating(false);
    }
  };

  const retireOther = (keep: "lsfg" | "mako" | "opti"): FrameGenStep[] => [
    ...(profile && keep !== "lsfg" ? [{ apply: () => saveLsfg(null), restore: () => saveLsfg(profile) }] : []),
    ...(makoProfile && keep !== "mako" ? [{ apply: () => saveMako(null), restore: restoreMako }] : []),
    ...(installedRoute && onApplyOptiscaler && keep !== "opti" ? [{ apply: () => onApplyOptiscaler("off", null), restore: () => onApplyOptiscaler("on", installedRoute) }] : []),
  ];
  const enableLossless = async (ready: LsfgStatus | null) => {
    if (!ready?.installed) setStatus(await installLsfg());
    await transitionFrameGen([
      { apply: () => saveLsfg({ multiplier: 2, flow_scale: 0.75, flow_manual: false, performance: true }), restore: () => saveLsfg(profile) },
      ...retireOther("lsfg"),
    ]);
    onOptiscaler("off", null);
    setSelection("lsfg");
  };

  const choose = (pick: Pick) => {
    if (blocked) return;
    setSelection(pick);
    if (pick !== "lsfg" && pick !== "mako" && pick !== "mako5") onOptiscaler(pick === "off" ? "off" : "on", pick === "off" ? null : pick);
  };
  const selectedActive = isMako ? makoPick === current : current === "lsfg" ? !!profile : current !== "off" && current === installedRoute && !profile && !makoProfile;
  const applySelection = () => run(async () => {
    if (blocked) return;
    if (isMako) {
      if (selectedActive) { await saveMako(null); setSelection("off"); }
      else {
        if (!mako?.supported || (makoEngine === 4 && !mako.dll) || mako.reason === "mako_identity_ambiguous") return;
        if (!(makoEngine === 5 ? mako.v5?.installed : mako.installed)) setMako(await installMako(makoEngine));
        if (makoProfile) { await saveMako({ ...makoProfile, engine: makoEngine }, true); return; }
        const start: MakoProfile = makoEngine === 5
          ? { engine: 5, mode: "fixed", multiplier: 2, target_fps: 120, max_multiplier: 3, flow: "balanced", fg_mode: "balanced", performance: false }
          : { engine: 4, mode: "fixed", multiplier: 2, target_fps: 120, max_multiplier: 3, flow: "balanced", performance: true };
        await transitionFrameGen([
          { apply: () => saveMako(start, true), restore: restoreMako },
          ...retireOther("mako"),
        ]);
        onOptiscaler("off", null);
      }
      return;
    }
    if (current === "lsfg") {
      if (profile) {
        await saveLsfg(null);
        setSelection("off");
      } else if (!status?.foreign && status?.dll && (!installedRoute || onApplyOptiscaler)) {
        await enableLossless(status);
      }
      return;
    }
    if (current === "off" && (profile || makoProfile) && !installedRoute) {
      if (profile) await saveLsfg(null);
      if (makoProfile) await saveMako(null);
      return;
    }
    if (!onApplyOptiscaler || optiscalerDisabled) return;
    const next = selectedActive ? "off" : current;
    await transitionFrameGen([
      ...retireOther("opti"),
      { apply: () => onApplyOptiscaler(next === "off" ? "off" : "on", next === "off" ? null : next), restore: () => onApplyOptiscaler(installedRoute ? "on" : "off", installedRoute) },
    ]);
    if (selectedActive) {
      setSelection("off");
      onOptiscaler("off", null);
    }
  }, !selectedActive && current !== "off");

  const lsfgUnavailable = current === "lsfg" && !!status?.unavailable;
  const needBranch = current === "lsfg" && !!status && !status.arm && status.lossless && !status.dll;
  const foreignBackup = !!status && !status.foreign && !!status.foreign_backup;
  const showControls = !!mako || !!offer.own || !!installedRoute || offer.options.length > 0 || !!profile || !!status?.foreign || foreignBackup || needBranch || lsfgUnavailable;

  const optionLabel = (label: string, icon?: ReactNode) => (
    <span ref={showFrameGenIcon} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      <span aria-hidden style={{ display: "inline-flex", width: 16, flexShrink: 0 }}>{icon}</span>
      <span>{label}</span>
    </span>
  );
  const options: { value: Pick; label: ReactNode }[] = [
    { value: "off", label: optionLabel(t("up.fg.pick.off")) },
    ...(mako ? (["mako5", "mako"] as const).map((value) => ({ value: value as Pick, label: optionLabel(MAKO_NAME[value], <GiSharkFin className="pdc-up-mako-icon" size={16} />) })) : []),
    ...offer.options.map((value) => ({ value: value as Pick, label:
      value === "lsfg" ? optionLabel("Lossless Scaling", <GiPlasticDuck className="pdc-up-lossless-icon" size={16} />) :
      value === "optiscaler" || value === "game" ? optionLabel(t("up.fg.pick.optiscaler"), <LuLayers className="pdc-up-optiscaler-icon" size={16} />) :
      value === "anr" ? optionLabel(t("up.fg.pick.anr"), <LuSparkles className="pdc-up-anr-icon" size={16} />) :
      optionLabel(t(`up.fg.pick.${value}`)),
    })),
  ];

  const restore = current === "lsfg" && foreignBackup && (
    <ListRow label={t("up.lsfg.restore")} busy={busy} onPress={() => void run(async () => {
      const restored = await restoreForeignLsfg();
      await clearLsfgLaunch(restored.cleared ?? []);
      setStatus(restored);
    })} />
  );

  return (
    <>
      {showControls && <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        <Label>{t("up.fg.title")}</Label>
        {options.length > 1 && (
          <PickerButton duo={duo} controlId={`${appid}:fg`} ready={status !== null}
            label={t("up.fg.title")}
            value={current}
            disabled={blocked}
            onChange={(pick) => void choose(pick)}
            options={options}
            badge={current === "optiscaler" ? <ExperimentalBadge>{t("up.fg.experimental")}</ExperimentalBadge>
              : current === "anr" ? <ExperimentalBadge>{t("up.fg.beta")}</ExperimentalBadge> : undefined}
          />
        )}
        {isMako && selectedActive && makoProfile && <MakoControls appid={appid} duo={duo} profile={makoProfile} disabled={blocked} onChange={(next) => void run(() => saveMako(next, true))} />}
        {isMako && mako?.reason === "mako_identity_ambiguous" && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.mako.identity")}</Notice>}
        {current === "mako" && !mako?.dll && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.mako.requirement")}</Notice>}
        {isMako && mako && !mako.supported && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.mako.unsupported")}</Notice>}
        {current === "lsfg" && profile && (
          <ListCard>
              <PickerButton
                duo={duo} controlId={`${appid}:multiplier`} showLabel label={t("up.lsfg.multiplier")}
                value={String(profile.multiplier)}
                disabled={blocked}
                options={MULTIPLIERS.map((m) => ({ value: String(m), label: `×${m}` }))}
                onChange={(m) => void run(() => saveLsfg({ ...profile, multiplier: Number(m) as LsfgProfile["multiplier"] }))}
              />
              <PickerButton
                duo={duo} controlId={`${appid}:flow`} showLabel label={t("up.lsfg.flow")}
                value={flowMode(profile)}
                disabled={blocked}
                options={FLOW_MODES.map((mode) => ({ value: mode, label: t(`up.lsfg.flow.${mode}`) }))}
                onChange={(mode) => void run(() => saveLsfg(mode === "manual"
                  ? { ...profile, flow_manual: true, flow_scale: profile.manual_scale ?? profile.flow_scale }
                  : { ...profile, flow_manual: false, flow_scale: FLOW_PRESETS[mode as Exclude<FlowMode, "manual">], manual_scale: flowMode(profile) === "manual" ? profile.flow_scale : profile.manual_scale }))}
              />
              {flowMode(profile) === "manual" && <>
                <FlowScale appid={appid} value={profile.flow_scale} disabled={blocked}
                  onCommit={(flowScale) => void run(() => saveLsfg({ ...profile, flow_manual: true, flow_scale: flowScale, manual_scale: flowScale }))} />
                <Note>{t("up.lsfg.flowScaleHint")}</Note>
              </>}
            <ListRow label={t("up.lsfg.light")} caption={t("up.lsfg.lightHint")} on={profile.performance} disabled={blocked}
              onPress={() => void run(() => saveLsfg({ ...profile, performance: !profile.performance }))} />
          </ListCard>
        )}
        {current === "off" && offer.own && <Notice icon={<LuLayers size={16} />}>{t("up.fg.own", { name: t(`up.fg.own.${offer.own}`) })}</Notice>}
        {(current === "game" || current === "optiscaler") && recommendedRoutes && !recommendedRoutes[current] && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.fg.notRecommended")}</Notice>}
        {current === "game" && dlssBridge && <Notice icon={<LuLayers size={16} />}>{t("up.fg.hint.dlss")}</Notice>}
        {current === "optiscaler" && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.fg.hint.opti")}</Notice>}
        {current === "anr" && <Notice icon={<LuSparkles size={16} />}>{t(installedRoute === "anr" ? "up.fg.hint.anrGame" : "up.fg.hint.anr")}</Notice>}
        {current === "anr" && anrSettings.map((entry) => <Notice key={entry.setting} icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.gameSetting", entry)}</Notice>)}
        {isMako && !makoProfile && makoLeftover.leftover && (
          <>
            <Notice icon={<LuArrowLeftRight size={16} />}>{t("up.mako.leftover")}</Notice>
            <Row><ActionButton label={t("up.mako.leftover.clear")} busy={busy} disabled={disabled || gameRunning} onPress={() => void run(makoLeftover.clear)} /></Row>
          </>
        )}
        {lsfgUnavailable && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.lsfg.armNoLayer")}</Notice>}
        {current === "lsfg" && status?.foreign && (
          <>
            <Notice icon={<LuArrowLeftRight size={16} />}>{t("up.lsfg.foreign")}</Notice>
            <Row><ActionButton label={t("up.lsfg.adopt")} busy={busy} disabled={disabled || !status.dll} onPress={() => void run(async () => { const adopted = await adoptForeignLsfg(); setStatus(adopted); })} /></Row>
          </>
        )}
        {(current !== "off" || !!profile || !!makoProfile || !!installedRoute) && !(current === "lsfg" && status?.foreign) && !(isMako && !makoProfile && makoLeftover.leftover) && (
          <ActionButton
            label={enginePhase ? t(`up.engine.${enginePhase}`) : activating ? t("up.activating") : t(selectedActive || current === "off" ? "up.deactivate" : installedRoute || profile || makoProfile ? "up.save" : "up.activate", { name: isMako ? MAKO_NAME[current] : current === "off" && makoPick ? MAKO_NAME[makoPick] : current === "lsfg" || (current === "off" && profile) ? "Lossless Scaling" : t(`up.fg.pick.${current === "off" ? installedRoute ?? "optiscaler" : current}`) })}
            busy={busy || enginePhase !== null}
            disabled={disabled || (isMako ? (!selectedActive && (!mako?.supported || (makoEngine === 4 && !mako.dll) || mako.reason === "mako_identity_ambiguous" || (!makoProfile && !!installedRoute && !onApplyOptiscaler))) : current === "lsfg" ? (lsfgUnavailable || !profile && (!status?.dll || (!!installedRoute && !onApplyOptiscaler))) : !(current === "off" && (profile || makoProfile) && !installedRoute) && (!onApplyOptiscaler || optiscalerDisabled))}
            onPress={() => void applySelection()}
          />
        )}
        {current === "mako" && mako?.dll && !mako.notice_dismissed && (
          <NoticeCard icon={<GiPlasticDuck size={16} />} tone={theme.color.accent} title={t("up.mako.notice.title")}
            description={t("up.mako.notice.body")} dismissLabel={t("up.mako.notice.dismiss")}
            onDismiss={() => void dismissMakoNotice().then(setMako).catch(() => {})} />
        )}
        {current === "lsfg" && branch?.supported && branch.available && branch.selected !== null && branch.selected !== "lsfg-vk" && (
          <ActionButton label={t("up.lsfg.switchBranch")} busy={busy} disabled={disabled} onPress={() => void run(async () => {
            const next = await switchLosslessBranch(15000, branchAbort.current?.signal);
            setBranch(next);
            setMessage(t("up.lsfg.branchChanged"));
          })} />
        )}
        {(needBranch || (current === "lsfg" && branch?.selected !== null && branch?.selected !== undefined && branch.selected !== "lsfg-vk")) && <Notice icon={<LuTriangleAlert size={16} />}>{t(branch?.selected === "lsfg-vk" ? "up.lsfg.branchWaiting" : "up.lsfg.needBranch")}</Notice>}
        {message && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{message}</span>}
      </div>}
      {renderAdvanced?.(restore)}
    </>
  );
};

async function clearLsfgLaunch(appids: string[]) {
  for (const id of appids) {
    const live = Number(id);
    const result = await applyManagedLaunch(id, live, "lsfg", {}, { isNonSteam: live > 0x7fffffff });
    if (!result.ok) throw new Error("launch_failed");
  }
}
