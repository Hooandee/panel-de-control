import { openFilePicker } from "@decky/api";
import { ConfirmModal, Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState, type FC, type ReactNode } from "react";
import { LuArrowLeftRight, LuInfo, LuCircleCheck, LuCircleDashed, LuTriangleAlert } from "react-icons/lu";

import {
  cancelUpscalersJob, configureUpscaler, getUpscalersGame,
  refreshUpscalerWiki, setUpscalersExe, uninstallUpscaler, verifyUpscaler, adoptForeignUpscaler, restoreForeignUpscaler,
} from "../api";
import { CompactBackAction } from "../components/CompactBackAction";
import { recordUiEvent } from "../system/uiEvents";
import { GameCover } from "../components/GameCover";
import { useSectionBack } from "../components/sectionBack";
import { useRunningGame } from "../tdp/useRunningGame";
import { CompareView, isComparing } from "./CompareView";
import { openIdentityModal } from "./IdentityModal";
import { readShortcutHint } from "./shortcutHint";
import { useI18n } from "../i18n";
import type { GameEntry } from "../launch/steamApi";
import { readAppDetails } from "../launch/steamApi";
import { CATALOG, pillVisible } from "../launch/catalog";
import type { GpuGen } from "../launch/proton";
import { useProtonCapabilities } from "../launch/useProtonCapabilities";
import { theme } from "../theme";
import {
  QUALITIES, badgeLabel, buildLabel, defaultChoice, lastOutputHeight, megabytes, renderHeight,
  buildBlocker, gameNotice, gameOutputHeight, protonFsr4Env, restoredChoice, steamMachineStrain,
} from "./model";
import { scalerSwitching } from "./scalerTransition";
import { MakoScaling } from "./MakoScaling";
import { getMakoStatus } from "../api";
import { ImageControls, type ImageControlsHandle } from "./ImageControls";
import { AdvancedIni } from "./AdvancedIni";
import { clearInstallRequest, onJobUpdate, readInstallJobId, readInstallRequest, startInstallJob, takeJobNotice, trackJob, waitForJobCompletion } from "./jobRunner";
import { DuringPlay, useUpscalerLive } from "./LivePanel";
import { pressUpscalerKeyInGame } from "./gameHotkey";
import { WikiFacts } from "./WikiFacts";
import { restartGame } from "./restartGame";
import { cancelPendingInstall, holdForRestart, onPendingInstalls, pendingInstall, queueForGameExit, runPendingInstall, takePendingFailure } from "./pendingInstall";
import { showModal } from "../navigation/showModal";
import { holdPage, onDraft, showGame, writeDraft, type PageDraft } from "./pageMemory";
import { LaunchMixNotice } from "./LaunchMixNotice";
import { JobProgress } from "./JobProgress";
import { FrameGenRow } from "./FrameGenRow";
import { useThemes } from "../themes/useThemes";
import { ModelPicker } from "./ModelPicker";
import { UserFiles } from "./UserFiles";
import { markPendingReinstall, takePendingReinstall } from "./userFileWatch";
import { replaceForeignInstallation } from "./foreignReplacement";
import {
  ActionButton, Fold, Label, ListCard, ListRow, Note, Notice, Row, SegmentRow, Skeleton, Spinner, statusColor,
} from "./parts";
import type { BuildInfo, GameDetail, UpscalerChoice, UpscalerJob, UpscalerStatus, UpscalersOverview, VerifyResult } from "./types";
import { upscalerErrorCode } from "./errorCode";

const INPUT_NAMES: Record<string, string> = { dlss: "DLSS", fsr31: "FSR 3.1", fsr2: "FSR 2", xess: "XeSS" };

// Games whose saved changes wait for the next launch; kept across leaving the page until the game closes.
const savedForNextLaunch = new Set<string>();
const RETRYABLE = new Set(["download_failed", "hash_mismatch", "size_mismatch", "no_space", "helixsr_failed"]);

type Translate = (key: string, params?: Record<string, string | number>) => string;

function errorText(t: Translate, code: string | null | undefined): string {
  const key = `up.error.${code}`;
  const text = t(key);
  return text === key ? t(code?.startsWith("prefix_") ? "up.error.prefix_failed" : "up.error.generic") : text;
}

function jobErrorText(t: Translate, job: UpscalerJob): string {
  const text = job.error === "no_space" && job.detail
    ? t("up.error.no_space", { mb: megabytes(Number(job.detail)) })
    : errorText(t, job.error);
  return job.detail && job.error?.startsWith("helixsr") ? `${text} (${job.detail})` : text;
}

export const GameView: FC<{
  game: GameEntry;
  overview: UpscalersOverview;
  onBack: () => void;
  onChanged: () => void;
  draft?: PageDraft<UpscalerChoice> | null;
}> = ({ game, overview, onBack, onChanged, draft }) => {
  const { t } = useI18n();
  const appid = String(game.liveAppid);
  const themes = useThemes();
  const duo = themes.cards.some((card) => card.id === "hooandee-duo" && card.active)
    || themes.snapshot.themes.some((theme) => theme.name === "Hooandee Duo" && theme.enabled);
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(draft?.advanced ?? false);
  const [choice, setChoice] = useState<UpscalerChoice>(() => pendingInstall(appid) ?? readInstallRequest(appid) ?? draft?.choice ?? defaultChoice(overview.preferred));
  const [queued, setQueued] = useState(() => pendingInstall(appid));
  useEffect(() => onPendingInstalls(() => {
    setQueued(pendingInstall(appid));
    const failed = takePendingFailure(appid);
    if (failed) setMessage(errorText(t, failed));
  }), [appid]);
  const [pendingModel, setPendingModel] = useState(false);
  const [switchingScaler, setSwitchingScaler] = useState(() => scalerSwitching(appid));
  useEffect(() => {
    const refresh = () => setSwitchingScaler(scalerSwitching(appid));
    refresh();
    window.addEventListener("pdc-scaler-switch", refresh);
    return () => window.removeEventListener("pdc-scaler-switch", refresh);
  }, [appid]);
  const [spatial, setSpatial] = useState(false);
  const [spatialInstalled, setSpatialInstalled] = useState(false);
  const spatialSelected = useRef(false);
  useEffect(() => {
    let alive = true;
    spatialSelected.current = false;
    setSpatial(false);
    setPendingModel(false);
    setSpatialInstalled(false);
    const refresh = (initial = false) => { void getMakoStatus(appid).then(status => {
      if (!alive) return;
      const installed = !!status.profiles[appid]?.scaling_enabled;
      setSpatialInstalled(installed);
      if (initial && !spatialSelected.current) setSpatial(installed);
    }).catch(() => {}); };
    const changed = () => refresh();
    refresh(true);
    window.addEventListener("pdc-mako-changed", changed);
    return () => { alive = false; window.removeEventListener("pdc-mako-changed", changed); };
  }, [appid]);
  const selectSpatial = (value: boolean) => { spatialSelected.current = true; setSpatial(value); };
  const keepDraft = useRef(!!draft);
  const initialDefault = useRef(!draft && !readInstallRequest(appid));
  const preferred = detail?.preferred ?? overview.preferred;
  const trace = (action: string, next: UpscalerChoice = choice, ok = true) => {
    recordUiEvent("upscalers", action, {
      appid, stage: action === "restart_result" ? "result" : "intent",
      build: next.build, model: next.model, quality: next.quality,
      sharpness: next.sharpness, fg: next.fg, fg_route: next.fg_route,
    }, ok);
  };
  const changeChoice = (next: UpscalerChoice) => {
    initialDefault.current = false;
    trace("select", next);
    setChoice(next);
    writeDraft(game.liveAppid, { choice: next, advanced });
  };
  const toggleAdvanced = () => {
    recordUiEvent("upscalers", "advanced", { appid, open: !advanced });
    setAdvanced(!advanced);
    writeDraft(game.liveAppid, { choice, advanced: !advanced });
  };
  useEffect(() => {
    showGame(game.liveAppid);
    return onDraft(game.liveAppid, (next) => {
      setChoice(next.choice as UpscalerChoice);
      setAdvanced(next.advanced);
    });
  }, [game.liveAppid]);
  useEffect(() => { writeDraft(game.liveAppid, { choice, advanced }); }, [game.liveAppid, choice, advanced]);
  const [trackedJob, setJob] = useState<UpscalerJob | null>(overview.job?.appid === appid ? overview.job : null);
  const job = trackedJob?.appid === appid ? trackedJob : null;
  const [message, setMessage] = useState<string | null>(() => {
    const notice = takeJobNotice(appid);
    if (job?.state === "error") return jobErrorText(t, job);
    return notice ? t(notice.key, notice.params) : null;
  });
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [applied, setAppliedState] = useState<"now" | "restart" | "restarting" | null>(
    savedForNextLaunch.has(appid) ? "restart" : null);
  const setApplied = (next: "now" | "restart" | "restarting" | null) => {
    if (next === "restart") savedForNextLaunch.add(appid);
    else if (next !== "restarting") savedForNextLaunch.delete(appid);
    setAppliedState(next);
  };
  const imageControls = useRef<ImageControlsHandle | null>(null);
  const [imageDirty, setImageDirty] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [confirmAntiCheat, setConfirmAntiCheat] = useState(false);
  const [foreignBusy, setForeignBusy] = useState(false);
  const foreignPending = useRef(false);
  const [compat, setCompat] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    readAppDetails(game.liveAppid).then((d) => { if (!cancelled) setCompat(d?.compatName ?? ""); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [game.liveAppid]);
  const capabilities = useProtonCapabilities(compat ?? "", compat === null);
  const protonEnv = capabilities.status === "ready"
    ? protonFsr4Env(CATALOG, (pill) => pillVisible(pill, capabilities.envs, overview.gpu as GpuGen))
    : null;
  const [comparing, setComparing] = useState(() => isComparing(appid));
  const runningGame = useRunningGame();
  const gameRunning = runningGame?.liveAppid === game.liveAppid;
  useEffect(() => {
    if (!gameRunning && savedForNextLaunch.has(appid)) {
      savedForNextLaunch.delete(appid);
      setAppliedState((last) => last === "restart" ? null : last);
    }
  }, [gameRunning, appid]);
  const mounted = useRef(true);
  const height = lastOutputHeight(detail?.history ?? []);
  const backOverride = useMemo(() => ({ label: t("up.back"), onBack }), [t, onBack]);
  const borrowedBack = useSectionBack(backOverride);

  const load = useCallback(async () => {
    try {
      const hint = game.isNonSteam ? await readShortcutHint(game.liveAppid, game.name) : null;
      const next = await getUpscalersGame(appid, hint);
      if (!mounted.current) return;
      setDetail(next);
      setLoadError(null);
      const request = pendingInstall(appid) ?? readInstallRequest(appid);
      if (request) setChoice(request);
      else if (next.install && !keepDraft.current) {
        setChoice(restoredChoice(next.install.build, next.install.options, overview.builds, next.preferred ?? overview.preferred));
      }
      else if (initialDefault.current && !next.install) {
        setChoice(defaultChoice(next.preferred ?? overview.preferred));
      }
      initialDefault.current = false;
      keepDraft.current = false;
    } catch (error) {
      if (mounted.current) setLoadError(upscalerErrorCode(error));
    }
  }, [appid, overview.preferred, overview.builds, game.isNonSteam, game.liveAppid, game.name]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const [wikiUpdating, setWikiUpdating] = useState(false);
  useEffect(() => {
    let done = false;
    const slow = setTimeout(() => { if (!done && mounted.current) setWikiUpdating(true); }, 300);
    refreshUpscalerWiki(appid)
      .then((result) => { if (result.updated && mounted.current) void load(); })
      .catch(() => undefined)
      .finally(() => { done = true; clearTimeout(slow); if (mounted.current) setWikiUpdating(false); });
    return () => clearTimeout(slow);
  }, [load]);

  useEffect(() => onJobUpdate(({ job: next, finished, notice }) => {
    if (next.appid !== appid || !mounted.current) return;
    setJob(next);
    if (!finished) return;
    takeJobNotice(appid);
    if (next.state === "error") {
      setMessage(jobErrorText(t, next));
    } else if (notice) {
      setMessage(t(notice.key, notice.params));
    }
    void load();
    onChanged();
  }), [appid, load, onChanged, t]);

  useEffect(() => {
    if (job?.state === "running") trackJob(job, { appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam });
  }, [job?.id]);

  const start = async (run: () => Promise<UpscalerJob>) => {
    setMessage(null);
    setVerify(null);
    try {
      const started = await run();
      setJob(started);
      trackJob(started, { appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam });
    } catch (error) {
      recordUiEvent("upscalers", "action_error", { appid, code: upscalerErrorCode(error) }, false);
      setMessage(errorText(t, upscalerErrorCode(error)));
      // HelixSR came out before the failure: the page must stop showing it installed.
      if (upscalerErrorCode(error) === "transition_failed_clean") { void load(); onChanged(); }
    }
  };

  const install = detail?.install ?? null;
  const running = job?.state === "running";
  const builds = overview.builds;
  const status = install?.status ?? null;
  const sameBuild = install?.build === choice.build;
  const solution = detail?.solutions?.[choice.build] ?? (detail?.install?.build === choice.build ? detail.solution : null);
  const qualityMode = qualityControl(detail, solution, sameBuild);
  const qualityChanged = qualityMode.mode === "panel" && install?.options.quality !== choice.quality;
  const modelChanged = (install?.options.model ?? builds.find((build) => build.id === install?.build)?.models?.[0] ?? null)
    !== (choice.model ?? builds.find((build) => build.id === choice.build)?.models?.[0] ?? null);
  const awaitingExit = !!queued && queued.build === choice.build && (queued.model ?? null) === (choice.model ?? null)
    && (!detail?.recipe_info?.quality_on_exit || (queued.quality ?? null) === (choice.quality ?? null));
  const dirty = !awaitingExit && (spatialInstalled || !install || !sameBuild || qualityChanged || install.options.sharpness !== choice.sharpness || modelChanged);
  const selectedFgPlan = solution ? solution.offered_fg_plan ?? solution.fg_plan : detail?.fg_plan;
  const routes = selectedFgPlan?.routes ?? {};
  const route = choice.fg_route ?? (selectedFgPlan?.route ?? selectedFgPlan?.source ?? "game");
  const selected = builds.find((b) => b.id === choice.build);
  const selectedModels = selected?.models;
  const helix = selected?.engine === "helixsr";
  const replacesFsr = selected?.way === "fsr" || selected?.engine === "proton" || selected?.engine === "dll";
  const installedBuild = builds.find((b) => b.id === install?.build);
  const externalHelix = !install && detail?.analysis.foreign_identity?.engine === "helixsr";
  const installedOptiscaler = !!install && installedBuild?.way !== "fsr" && installedBuild?.engine !== "proton" && installedBuild?.engine !== "dll";
  const installedRoute = install?.options.fg_route ?? detail?.fg_plan?.route ?? detail?.fg_plan?.source ?? null;
  const scalerChoice = { ...choice, fg: install?.options.fg ?? "off" as const, fg_route: install?.options.fg_route ?? null };
  const installSelected = () => startInstallJob({ appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam }, {
    ...scalerChoice, ...(replacesFsr ? { fg: "off" as const } : {}), confirm_anti_cheat: confirmAntiCheat,
    ...(selected?.engine === "proton" && protonEnv ? { env: protonEnv } : {}),
  });
  const reinstall = () => start(installSelected);
  // A user file changed (here or while this page was closed): it goes into the installed game once nothing blocks it.
  useEffect(() => {
    // A queued install for this game already carries the new file.
    if (detail?.install && !gameRunning && job?.state !== "running" && !pendingInstall(appid) && takePendingReinstall(appid)) reinstall();
  }, [detail?.install, gameRunning, job?.state]);
  const retry = () => {
    const request = job ? readInstallRequest(appid, job.id) : null;
    trace("retry", request ?? choice);
    return start(request
      ? () => startInstallJob({ appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam }, request)
      : installSelected);
  };
  const adoptAndInstall = async () => {
    if (foreignPending.current || running || gameRunning || !selected?.available
      || !detail?.analysis.target || detail.updating || buildBlocker(selected, detail.analysis.inputs, protonEnv)
      || (detail.analysis.anti_cheat && !confirmAntiCheat)) return;
    foreignPending.current = true;
    setForeignBusy(true);
    try {
      await replaceForeignInstallation(() => adoptForeignUpscaler(appid), installSelected, start, async () => {
        await load();
        onChanged();
      });
    } finally {
      foreignPending.current = false;
      if (mounted.current) setForeignBusy(false);
    }
  };

  const apply = async () => {
    trace("apply");
    if (gameRunning && install && !spatialInstalled && (!sameBuild || modelChanged || (qualityChanged && !!detail?.recipe_info?.quality_on_exit))) {
      // The running game holds OptiScaler's files (and REFramework rewrites its quality on exit): it goes in as soon as it closes.
      queueForGameExit({ appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam }, {
        ...scalerChoice, ...(replacesFsr ? { fg: "off" as const } : {}), confirm_anti_cheat: confirmAntiCheat,
        ...(selected?.engine === "proton" && protonEnv ? { env: protonEnv } : {}),
      });
      setMessage(null);
      setApplied(null);
      return;
    }
    if (install && sameBuild && !spatialInstalled) {
      setMessage(null);
      setApplied(null);
      try {
        const requestId = readInstallJobId(appid);
        const result = await configureUpscaler(appid, scalerChoice);
        if (modelChanged) setVerify(null);
        if (requestId) clearInstallRequest(appid, requestId);
        if (gameRunning) setApplied(result.live ? "now" : "restart");
        await load();
        onChanged();
      } catch (error) {
        setMessage(errorText(t, upscalerErrorCode(error)));
      }
      return;
    }
    await reinstall();
  };

  const applyFrameGeneration = async (fg: "on" | "off", fg_route: UpscalerChoice["fg_route"]) => {
    trace("frame_generation", { ...choice, fg, fg_route });
    if (blocked || running) throw new Error("blocked");
    const configureInstalled = !!install && (sameBuild || fg === "off");
    const fgSolution = detail?.solutions?.[configureInstalled ? install!.build : choice.build];
    const next = { ...(configureInstalled ? restoredChoice(install!.build, install!.options, builds, preferred) : choice), fg, fg_route };
    if (configureInstalled) {
      const requestId = readInstallJobId(appid);
      const recoveryOnly = fg === "off" && install?.options.fg === "on" && !!fgSolution
        && (!!fgSolution.blocked_reason || !installedRoute || !fgSolution.fg_plan?.routes?.[installedRoute]);
      const result = await configureUpscaler(appid, recoveryOnly ? { fg: "off" } : next);
      if (requestId) clearInstallRequest(appid, requestId);
      if (gameRunning) setApplied(result.live ? "now" : "restart");
      keepDraft.current = true;
      changeChoice({ ...choice, fg, fg_route });
      await load();
      onChanged();
    } else if (fg === "on") {
      const started = await startInstallJob({ appid, liveAppid: game.liveAppid, isNonSteam: game.isNonSteam }, { ...next, confirm_anti_cheat: confirmAntiCheat });
      setJob(started);
      await waitForJobCompletion(started.id);
    }
  };

  const saveAll = async () => {
    // Image settings go first: a new version carries the saved sharpness over into its fresh INI.
    if (imageDirty && !(await imageControls.current?.save())) return;
    if (dirty) await apply();
  };

  const discard = () => {
    trace("discard");
    cancelPendingInstall(appid);
    if (install) changeChoice(restoredChoice(install.build, install.options, builds, preferred));
  };

  const askRestart = () => {
    trace("restart_prompt");
    holdPage();
    showModal(
      <ConfirmModal
        strTitle={t("up.restart.title")}
        strDescription={t("up.restart.body", { name: game.name })}
        strOKButtonText={t("up.restart.ok")}
        strCancelButtonText={t("up.bulk.cancel")}
        onOK={async () => {
          setApplied("restarting");
          const release = holdForRestart(appid);
          let ok = false;
          let failure: string | null = null;
          try {
            ok = await restartGame(game.liveAppid, () => runPendingInstall(appid));
          } catch (error) {
            ok = true;
            failure = upscalerErrorCode(error);
          } finally {
            release();
          }
          trace("restart_result", choice, ok);
          if (!mounted.current) return;
          setApplied(null);
          if (failure) setMessage(errorText(t, failure));
          else if (!ok) setMessage(t("up.restart.failed"));
        }}
      />,
      window,
    );
  };

  const foreignAction = async (action: (id: string) => Promise<unknown>) => {
    setMessage(null);
    try {
      await action(appid);
      await load();
      onChanged();
    } catch (error) {
      setMessage(errorText(t, upscalerErrorCode(error)));
    }
  };

  const check = async () => {
    setVerifying(true);
    try {
      setVerify(await verifyUpscaler(appid));
      await load();
      onChanged();
    } catch {
      setMessage(t("up.error.generic"));
    } finally {
      if (mounted.current) setVerifying(false);
    }
  };

  const pickExe = async () => {
    const picked = await openFilePicker(0 as never, detail?.analysis.target ?? "/home", true, true, undefined, ["exe"]).catch(() => null);
    if (!picked?.realpath) return;
    try {
      setDetail(await setUpscalersExe(appid, picked.realpath));
    } catch {
      setMessage(t("up.error.invalid_exe"));
    }
  };

  const [counterStyleFailed, setCounterStyleFailed] = useState(false);
  const nextCounterStyle = async () => {
    setCounterStyleFailed(false);
    try {
      await pressUpscalerKeyInGame(appid, "fps_style");
    } catch {
      setCounterStyleFailed(true);
    }
  };

  const playing = !!install && gameRunning && !running;
  const [live, setGenerating] = useUpscalerLive(appid, playing, status === "pending" ? check : undefined);

  const facts = verify?.facts ?? detail?.history[detail.history.length - 1]?.facts;
  const render = facts?.resolution?.render[1] ?? null;
  const output = facts?.resolution?.output[1] ?? null;
  const blocked = switchingScaler || foreignBusy || !detail?.analysis.target || !!detail.updating || (detail.analysis.foreign && !install)
    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat);
  const inputs = solution?.inputs ?? detail?.analysis.inputs ?? {};
  const blockedBuilds = builds.filter((b) => b.available && b.supported && buildBlocker(b, inputs, protonEnv));
  const coming = builds.filter((b) => !b.available && b.supported);
  const preferredBuild = builds.find((b) => b.id === preferred && b.available);
  const runs = badgeLabel(installedBuild, install?.options.model, install?.build ?? "").full;
  const uses = [...new Set(Object.keys(inputs).map((k) => INPUT_NAMES[k]).filter(Boolean))];
  const qualityName = (q: UpscalerChoice["quality"]) => (q ? t(`up.quality.${q}`) : t("up.quality.game"));
  const installedEngine = installedBuild?.engine ?? "optiscaler";
  const selectedEngine = selected?.engine ?? "optiscaler";
  const optiscalerRecipe = !spatial && !pendingModel && !externalHelix && selectedEngine === "optiscaler";
  const recommendedInputKey = solution ? solution.recommended_input : detail?.recipe_info?.recommended_input;
  const scalerSeenWorking = sameBuild && (status === "active" || (playing && live.active));
  // Locked quality already names the input to pick, right under the selector.
  const inputHintShown = !scalerSeenWorking && qualityMode.mode !== "locked";
  const recommendedInput = optiscalerRecipe && !detail?.native && recommendedInputKey && inputHintShown
    ? INPUT_NAMES[recommendedInputKey] : null;
  const notice = detail && !detail.native ? gameNotice(detail.identity?.steam_appid ?? appid) : null;
  const strain = detail && !detail.native && !spatial ? steamMachineStrain(overview.device, gameOutputHeight(detail?.history ?? [], overview.display), selected, choice.quality) : null;
  const recipeBlocked = !!solution?.blocked_reason || (optiscalerRecipe && !solution && !!detail?.recipe_info?.blocked);
  const automaticLuma = optiscalerRecipe && !detail?.recipe_info?.luma_detected && !!detail?.recipe_info?.automatic?.includes("Luma");
  const modeChanged = installedEngine !== selectedEngine && [installedEngine, selectedEngine].every((engine) => engine === "dll" || engine === "optiscaler");
  const pendingBuildLabel = (build: BuildInfo | undefined, model: string | null | undefined, fallback: string) => {
    if (!build) return fallback;
    const name = buildLabel({ ...build, channel: undefined });
    const variant = build.models?.length ? model ?? build.models[0] : null;
    return variant ? `${name} ${variant === "lite" ? "Lite" : t(`up.model.${variant}`)}` : name;
  };
  const versionChangeLabel = (label: string, engine: string) => modeChanged ? `${label} (${engine === "dll" ? t("up.mode.dll") : "OptiScaler"})` : label;
  const changes = !install ? [] : [
    !sameBuild && t("up.change.version", { from: versionChangeLabel(pendingBuildLabel(installedBuild, install.options.model, install.build), installedEngine), to: versionChangeLabel(pendingBuildLabel(selected, choice.model, choice.build), selectedEngine) }),
    qualityChanged && t("up.change.quality", { from: qualityName(install.options.quality), to: qualityName(choice.quality) }),
    modelChanged && !!installedBuild?.models?.length && !!selectedModels?.length && t("up.change.model", { from: t(`up.model.${install.options.model ?? installedBuild.models[0]}`), to: t(`up.model.${choice.model ?? selectedModels?.[0] ?? "lite"}`) }),
  ].filter((line): line is string => !!line);

  const subtitle = !detail ? null
    : detail.native ? null
    : playing ? t("up.sub.playing")
    : install ? runs
    : detail.analysis.foreign ? externalHelix ? "" : t("up.sub.foreign")
    : uses.length ? t(preferredBuild ? "up.sub.usesBetter" : "up.sub.uses", { name: uses.join(", ") })
    : null;

  return (
    <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {!borrowedBack && <Row><CompactBackAction onBack={onBack} label={t("up.back")} /></Row>}

      <div style={{ display: "flex", gap: theme.space.md, alignItems: "center", animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
        <GameCover urls={game.coverUrls} name={game.name} width={48} />
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: theme.font.body + 1, lineHeight: 1.2, color: theme.color.textPrimary }}>{game.name}</div>
          {subtitle && <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textMuted }}>{subtitle}</span>}
        </div>
      </div>

      {detail ? (
        <div style={{ ...theme.card, padding: `${theme.space.md}px`, display: "flex", flexDirection: "column", gap: 6 }}>
          {spatialInstalled && (spatial || !install) ? (
            <StatusLine title={t("up.state.installed", { name: "Mako" })} />
          ) : detail.native ? (
            <StatusLine title={t("up.native.title")} sub={t("up.native")} />
          ) : playing ? (
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                <StatusLine icon={<StatusIcon status={status} />} title={runs} />
                {live.render !== null && live.output !== null && (
                  <span style={{ fontSize: theme.font.caption + 2, color: theme.color.textMuted, fontVariantNumeric: "tabular-nums" }}>
                    {t("up.res.arrow", { from: live.render, to: live.output })}
                  </span>
                )}
              </div>
              <div style={{
                display: "flex", flexDirection: "column", alignItems: "center", minWidth: 64, padding: `6px ${theme.space.md}px`,
                borderRadius: 10, background: "rgba(255,255,255,0.06)",
              }}>
                <span style={{ fontSize: 24, lineHeight: 1, fontWeight: 700, color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums" }}>
                  {live.fps === null ? "–" : Math.round(live.fps)}
                </span>
                <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, letterSpacing: 0.6, marginTop: 2 }}>{t("up.live.fps")}</span>
              </div>
            </div>
          ) : install ? (
            <StatusLine
              icon={<StatusIcon status={status} />}
              title={status === "active" ? t("up.state.working", { name: runs }) : status === "broken" ? t("up.status.broken") : t("up.state.installed", { name: runs })}
              sub={status === "active" && render && output
                ? t(render < output ? "up.state.checked" : "up.state.checkedNative", { from: render, to: output })
                : status === "active" ? undefined : installedBuild?.engine === "dll" && status === "not_run"
                  ? t("up.status.dll_not_run") : t(`up.status.${status}`)}
              tone={status === "broken" ? "danger" : status === "loaded" ? "warn" : undefined}
            />
          ) : detail.analysis.foreign ? (
            <StatusLine icon={<LuArrowLeftRight size={17} />} title={detail.analysis.foreign_identity?.engine === "helixsr" ? `HelixSR${detail.analysis.foreign_identity.variant === "unknown" ? "" : ` ${detail.analysis.foreign_identity.variant.toUpperCase()}`}` : t("up.foreign.title")} sub={detail.analysis.foreign_identity?.engine === "helixsr" ? t("up.helix.foreign", { name: "HelixSR" }) : t("up.foreign.body")} />
          ) : (
            <StatusLine
              title={t("up.state.none")}
            />
          )}
          <LaunchMixNotice liveAppid={game.liveAppid} scaler={install ? runs : detail.analysis.foreign_identity?.engine === "helixsr" ? "HelixSR" : null} />
          {!detail.native && !externalHelix && <ModelPicker onPendingChoice={setPendingModel} gpu={overview.gpu} duo={duo} appid={appid} spatial={spatial} onSpatial={selectSpatial} builds={builds} choice={choice} inputs={inputs} protonEnv={protonEnv} dllTargets={detail.analysis.dll_targets}
            disabled={running || foreignBusy} onChange={changeChoice} />}
          {!detail.native && !spatial && selectedEngine === "optiscaler" && !!detail.recipe_info?.user_files?.length && (
            <UserFiles appid={appid} files={detail.recipe_info.user_files} disabled={running || foreignBusy}
              onDetail={(next) => { if (next.install) markPendingReinstall(appid); setDetail(next); }} />
          )}
          {(detail.native || externalHelix) && <ListRow label="Mako" chevron disabled={running || foreignBusy} onPress={() => selectSpatial(!spatial)} />}
          {wikiUpdating && (
            <span style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <Spinner size={10} /> {t("up.wiki.updating")}
            </span>
          )}
          {detail.launcher && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t(`up.launcher.${detail.launcher}`)}</span>}
          {detail.shortcut && !detail.native && (
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <span style={{ flex: 1 }}>
                {detail.identity?.steam_appid
                  ? t("up.identity.known", { name: detail.identity.name ?? String(detail.identity.steam_appid) })
                  : t("up.identity.unknown")}
              </span>
              <span style={{ width: 92 }}>
                <ActionButton label={t("up.identity.change")} onPress={() => openIdentityModal(appid, detail.identity?.name ?? game.name, setDetail)} />
              </span>
            </div>
          )}
        </div>
      ) : !loadError && <Skeleton height={64} />}

      {!detail && !loadError && (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
          <Spinner size={12} /> {t("up.detect.analyzing")}
        </div>
      )}
      {loadError === "not_installed" && <Note tone="warn">{t("up.error.missingFolder")}</Note>}
      {loadError && loadError !== "not_installed" && <Row><ActionButton label={t("load.retry")} onPress={() => void load()} /></Row>}

      {detail && !detail.native && (
        <>
          {detail.analysis.foreign && detail.analysis.foreign_identity?.engine !== "helixsr" && !install && (
            <Row><ActionButton label={t("up.foreign.adopt")} busy={foreignBusy} disabled={running || gameRunning || !selected?.available || !detail.analysis.target || !!detail.updating || !!buildBlocker(selected, detail.analysis.inputs, protonEnv) || (detail.analysis.anti_cheat && !confirmAntiCheat)} onPress={() => void adoptAndInstall()} /></Row>
          )}
          {!detail.analysis.target && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.error.no_exe")}</Notice>}
          {detail.updating && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t(detail.updating === "running" ? "up.error.updating" : "up.error.update_pending")}</Notice>}
          {detail.analysis.target && uses.length === 0 && !solution?.input_reconciled && !detail.recipe_info?.needs.includes("mod") && !detail.recipe_info?.user_files?.length && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.detect.noinputs")}</Notice>}
          {detail.recipe_info?.broken && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.broken")}</Notice>}
          {detail.recipe_info?.needs.filter((need) => !(need === "mod" && detail.recipe_info?.user_files?.length)).filter((need) => need !== "luma" || (optiscalerRecipe && !detail.recipe_info?.luma_detected && !automaticLuma)).map((need) => <Notice key={need} icon={<LuTriangleAlert size={16} />} tone="warn">{t(`up.recipe.need.${need}`)}</Notice>)}
          {!spatial && selectedEngine === "optiscaler" && detail.recipe_info?.game_settings?.map((entry) => (
            <Notice key={entry.setting} icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.gameSetting", entry)}</Notice>
          ))}
          {!spatial && selectedEngine === "optiscaler" && detail.recipe_info?.quality_on_exit && overview.display && (
            <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.fullResolution", { size: `${Math.max(...overview.display)}x${Math.min(...overview.display)}` })}</Notice>
          )}
          {automaticLuma && <Note>{t("up.recipe.automatic.luma")}</Note>}
          {install && optiscalerRecipe && !running && ["missing", "pending"].includes(detail.recipe_info?.windows_components ?? "") && (
            <>
              <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.windowsComponents")}</Notice>
              <Row><ActionButton label={t("load.retry")} disabled={blocked || gameRunning} onPress={reinstall} /></Row>
            </>
          )}
          {recipeBlocked && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.blocked")}</Notice>}
          {detail.recipe_info && (
            <WikiFacts appid={appid} info={detail.recipe_info} installed={!!install} onApplied={() => void load()} />
          )}
          {detail.analysis.anti_cheat && !install && (
            <>
              <Notice icon={<LuTriangleAlert size={16} />} tone="danger">{t("up.error.anti_cheat")}</Notice>
              <SegmentRow
                value={confirmAntiCheat ? "yes" : null}
                onChange={() => setConfirmAntiCheat(!confirmAntiCheat)}
                options={[{ value: "yes", label: t("up.error.anti_cheat.confirm") }]}
              />
            </>
          )}
        </>
      )}


      {detail && spatial && <MakoScaling key={appid} appid={appid} liveAppid={game.liveAppid} isNonSteam={game.isNonSteam}
        disabled={running || foreignBusy || gameRunning || switchingScaler || !!detail.updating} gameRunning={gameRunning} mixed={!install && detail.analysis.foreign} onChanged={() => { void load(); onChanged(); }} />}

      {detail && !pendingModel && !spatial && !detail.native && !externalHelix && !replacesFsr && qualityMode.mode !== "game" && (
        <>
          <Label>{t("up.section.quality")}</Label>
          <SegmentRow compact disabled={qualityMode.mode === "locked"}
            value={choice.quality && QUALITIES.includes(choice.quality) ? choice.quality : null}
            onChange={(quality) => changeChoice({ ...choice, quality })}
            options={QUALITIES.map((q) => ({ value: q, label: t(`up.quality.${q}`), caption: height === undefined ? undefined : `${renderHeight(height, q)}p` }))}
          />
        </>
      )}
      {detail && !pendingModel && !spatial && !detail.native && !externalHelix && (qualityMode.mode === "game" || replacesFsr) && <Note>{t("up.quality.inGame")}</Note>}
      {detail && !pendingModel && !spatial && qualityMode.mode === "locked" && <Note>{t("up.quality.useInput", { input: qualityMode.input })}</Note>}
      {notice && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t(notice)}</Notice>}
      {strain && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t(`up.steamMachine.${strain}`)}</Notice>}
      {recommendedInput && <Notice icon={<LuInfo size={16} />}>
        {t("up.input.recommended", { input: recommendedInput, name: badgeLabel(selected, choice.model, choice.build).full })}
      </Notice>}
      {detail && !spatial && !detail.native && (installedOptiscaler || detail.analysis.foreign_identity?.engine === "helixsr") && (
        <ImageControls key={`${appid}:${detail.analysis.target}:${install?.build ?? "foreign"}`}
          appid={appid} disabled={running || foreignBusy || (gameRunning && !installedOptiscaler) || switchingScaler || !!detail.updating}
          gameRunning={gameRunning} revision={JSON.stringify(install?.options ?? null)}
          ref={imageControls} onDirty={setImageDirty}
          onSavedForNextLaunch={() => setApplied("restart")} />
      )}
      {detail && !detail.native && helix && <Note>{t("up.helix.pick.fsr")}</Note>}
      {detail && !detail.native && selected?.engine === "proton" && <Note>{t("up.proton.note")}</Note>}

      {detail && !pendingModel && !spatial && !detail.native && !externalHelix && !running && (status === "broken" || dirty || imageDirty || install) && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, paddingTop: theme.space.sm, borderTop: `1px solid ${theme.color.hairline}` }}>
          {status === "broken" ? (
            <Row><ActionButton primary label={t("up.repair")} onPress={reinstall} disabled={blocked} /></Row>
          ) : !install ? (
            <Row>
              <ActionButton primary label={t("up.activate", { name: badgeLabel(selected, choice.model, choice.build).full })} onPress={apply} disabled={blocked} />
            </Row>
          ) : dirty || imageDirty ? (
            <>
              {dirty && changes.map((line) => (
                <span key={line} style={{ fontSize: theme.font.caption + 1, color: theme.color.textMuted, textAlign: "center" }}>{line}</span>
              ))}
              <Row>
                <ActionButton label={t("up.discard")} onPress={() => { discard(); imageControls.current?.discard(); }} />
                <ActionButton primary label={t("up.save")} onPress={saveAll} disabled={blocked} />
              </Row>
            </>
          ) : (
            <Row><ActionButton label={t("up.deactivate", { name: runs })} disabled={blocked || gameRunning} onPress={() => start(() => uninstallUpscaler(appid))} /></Row>
          )}
        </div>
      )}

      {applied === "now" && !message && <Note>{t("up.live.appliedNow")}</Note>}
      {(applied === "restart" || awaitingExit) && !message && gameRunning && (
        <InView>
          <Note>{t(awaitingExit ? "up.live.appliedOnExit" : "up.live.appliedNext")}</Note>
          <Row>
            {awaitingExit && <ActionButton label={t("up.discard")} onPress={discard} />}
            <ActionButton primary={awaitingExit} label={t("up.restart.button")} onPress={askRestart} />
          </Row>
        </InView>
      )}
      {applied === "restarting" && <Note>{t("up.restart.doing")}</Note>}
      {detail && playing && !comparing && (
        <DuringPlay
          appid={appid}
          optiscaler={installedOptiscaler}
          fpsCounter={detail.recipe_info?.fps_counter !== false}
          fg={installedOptiscaler && install?.options.fg === "on"}
          live={live}
          onGenerating={setGenerating}
          onCompare={() => setComparing(true)}
        />
      )}
      {detail && install && comparing && (
        <CompareView appid={appid} gameRunning={gameRunning} onClose={() => setComparing(false)} />
      )}

      {detail && (
        <FrameGenRow duo={duo} disabled={running || foreignBusy}
          onApplyOptiscaler={applyFrameGeneration} optiscalerDisabled={blocked}
          appid={appid}
          liveAppid={game.liveAppid}
          isNonSteam={game.isNonSteam}
          gameRunning={gameRunning}
          recommendedRoutes={solution ? solution.fg_plan?.routes ?? {} : undefined}
          routes={detail.native || !selectedFgPlan || replacesFsr ? {} : routes}
          inputs={detail.native ? {} : inputs}
          optiscaler={{ fg: choice.fg ?? "off", route }}
          installedRoute={install?.options.fg === "on" ? install.options.fg_route ?? detail.fg_plan?.route ?? detail.fg_plan?.source ?? "game" : null}
          gpu={overview.gpu}
          onOptiscaler={(fg, fg_route) => changeChoice({ ...choice, fg, fg_route: fg_route ?? choice.fg_route ?? null })}
          renderAdvanced={(restore) => detail.native ? restore && (
            <>
              <div role="separator" style={{ borderTop: `1px solid ${theme.color.hairline}`, marginTop: theme.space.md, paddingTop: theme.space.sm }} />
              <Fold label={t("up.advanced")} open={advanced} onToggle={toggleAdvanced} />
              {advanced && <ListCard>{restore}</ListCard>}
            </>
          ) : (
            <>
              <div role="separator" style={{ borderTop: `1px solid ${theme.color.hairline}`, marginTop: theme.space.md, paddingTop: theme.space.sm }} />
              <Fold label={t("up.advanced")} open={advanced} onToggle={toggleAdvanced} />
              {advanced && (
                <>
                  <ListCard>
                    {restore}
                    {detail.foreign_backup && !install && !detail.analysis.foreign && (
                      <ListRow label={t("up.foreign.restore")} disabled={foreignBusy || running || gameRunning} onPress={() => void foreignAction(restoreForeignUpscaler)} />
                    )}
                    {playing && installedOptiscaler && detail.recipe_info?.fps_counter !== false && (
                      <ListRow label={t("up.play.fpsStyle")} chevron onPress={() => void nextCounterStyle()} />
                    )}
                    {installedOptiscaler && !running && <AdvancedIni appid={appid} />}
                    <ListRow
                      label={t("up.exe")}
                      detail={detail.analysis.manual && detail.analysis.exe ? detail.analysis.exe.split("/").pop() : t("up.exe.auto")}
                      chevron
                      disabled={running}
                      onPress={() => void pickExe()}
                    />
                    {detail.analysis.manual && (
                      <ListRow label={t("up.detect.auto")} disabled={running} onPress={async () => setDetail(await setUpscalersExe(appid, null))} />
                    )}
                    {install && !running && <ListRow label={t("up.verify")} chevron busy={verifying} onPress={() => void check()} />}
                    {install && !running && (
                      <ListRow danger label={t("up.remove")} caption={t("up.remove.caption")} onPress={() => start(() => uninstallUpscaler(appid))} />
                    )}
                  </ListCard>
                  {counterStyleFailed && <Note tone="warn">{t("up.live.failed")}</Note>}
                  {(selectedModels?.length ?? 0) > 1 && <Note>{t("up.model.help")}</Note>}
                  {blockedBuilds.map((b) => (
                    <Note key={b.id}>{t(buildBlocker(b, inputs, protonEnv) === "needsProton" ? "up.proton.needsProton" : "up.helix.needsFsr31", { name: buildLabel(b) })}</Note>
                  ))}
                  {coming.map((b) => <Note key={b.id}>{t("up.build.soonLine", { name: buildLabel(b) })}</Note>)}
                  {detail.history.length > 1 && (
                    <>
                      <Label>{t("up.history")}</Label>
                      {[...detail.history].reverse().slice(0, 5).map((entry) => {
                        const build = builds.find((b) => b.id === entry.build);
                        return (
                          <div key={`${entry.at}`} style={{ display: "flex", justifyContent: "space-between", gap: theme.space.xs, fontSize: theme.font.caption }}>
                            <span style={{ textDecoration: entry.result === "loaded" ? "line-through" : "none" }}>{build ? buildLabel(build) : entry.build}</span>
                            <span style={{ color: statusColor(entry.result) }}>{t(`up.history.${entry.result}`)}</span>
                          </div>
                        );
                      })}
                    </>
                  )}
                </>
              )}
            </>
          )}
        />
      )}

      {running && job && <JobProgress job={job} />}
      {running && <Row><ActionButton label={t("up.cancel")} onPress={async () => { await cancelUpscalersJob(); }} /></Row>}
      {message && <InView><Note tone="warn">{message}</Note></InView>}
      {!running && job?.state === "error" && job.kind === "install" && RETRYABLE.has(job.error ?? "") && (
        <Row><ActionButton label={t("up.retry")} onPress={retry} /></Row>
      )}


    </Focusable>
  );
};


const StatusIcon: FC<{ status: UpscalerStatus | null }> = ({ status }) => {
  if (status === "active") return <LuCircleCheck size={17} color={theme.color.ok} />;
  if (status === "broken") return <LuTriangleAlert size={17} color={theme.color.danger} />;
  if (status === "loaded") return <LuTriangleAlert size={17} color={theme.color.warn} />;
  return <LuCircleDashed size={17} color={theme.color.textMuted} />;
};

const StatusLine: FC<{ icon?: ReactNode; title: string; sub?: string; tone?: "warn" | "danger" }> = ({ icon, title, sub, tone }) => (
  <>
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
      {icon && <span style={{ display: "inline-flex", flexShrink: 0 }}>{icon}</span>}
      <span style={{ fontWeight: 700, fontSize: theme.font.body + 1, color: theme.color.textPrimary }}>{title}</span>
    </div>
    {sub && (
      <span style={{
        fontSize: theme.font.caption + 1, lineHeight: 1.35,
        color: tone === "danger" ? theme.color.danger : tone === "warn" ? theme.color.warn : theme.color.textMuted,
      }}>{sub}</span>
    )}
  </>
);

/** Brings a just-shown result into view: saving reloads the page and leaves it scrolled to the top. */
const InView: FC<{ children: ReactNode }> = ({ children }) => {
  const box = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" }), 250);
    return () => window.clearTimeout(timer);
  }, []);
  return <div ref={box} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>{children}</div>;
};

type QualityControl = { mode: "panel" } | { mode: "locked"; input: string } | { mode: "game" };

/** Who sets the render size: Panel through OptiScaler, nobody yet because the game uses its own FSR, or the game. */
function qualityControl(detail: GameDetail | null, solution: { quality: { owner: string }; recommended_input?: string | null } | null | undefined,
  sameBuild: boolean): QualityControl {
  if (solution?.quality.owner === "game") return { mode: "game" };
  const inputs = detail?.analysis.inputs ?? {};
  const asking = ["dlss", "xess"].filter((kind) => (inputs as Record<string, unknown>)[kind]);
  const check = sameBuild ? detail?.install?.quality_check : null;
  if (check?.result === "respected") return { mode: "panel" };
  const onlyOwnFsr = !asking.length && ["fsr31", "fsr2"].some((kind) => (inputs as Record<string, unknown>)[kind]);
  if (onlyOwnFsr) return { mode: "game" };
  if (check?.result === "ignored") {
    const preferred = solution?.recommended_input && asking.includes(solution.recommended_input) ? solution.recommended_input : asking.includes("xess") ? "xess" : "dlss";
    return { mode: "locked", input: INPUT_NAMES[preferred] };
  }
  return { mode: "panel" };
}
