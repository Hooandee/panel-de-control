import { openFilePicker } from "@decky/api";
import { ConfirmModal, Focusable, Navigation } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState, type FC, type ReactNode } from "react";
import { LuArrowLeftRight, LuCircleCheck, LuCircleDashed, LuTriangleAlert } from "react-icons/lu";

import {
  cancelUpscalersJob, configureUpscaler, getUpscalersGame, installUpscaler, pressUpscalerKey,
  refreshUpscalerWiki, setUpscalersExe, uninstallUpscaler, verifyUpscaler, adoptForeignUpscaler, restoreForeignUpscaler,
} from "../api";
import { CompactBackAction } from "../components/CompactBackAction";
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
  QUALITIES, badgeLabel, buildLabel, defaultChoice, megabytes, renderHeight,
  buildBlocker, downloadPace, protonFsr4Env, restoredChoice, type PaceSample,
} from "./model";
import { AdvancedIni } from "./AdvancedIni";
import { onJobUpdate, trackJob } from "./jobRunner";
import { DuringPlay, useUpscalerLive } from "./LivePanel";
import { WikiFacts } from "./WikiFacts";
import { restartGame } from "./restartGame";
import { showModal } from "../navigation/showModal";
import { holdPage, onDraft, showGame, writeDraft, type PageDraft } from "./pageMemory";
import { FrameGenRow } from "./FrameGenRow";
import { ModelPicker } from "./ModelPicker";
import { replaceForeignInstallation } from "./foreignReplacement";
import {
  ActionButton, Fold, Label, ListCard, ListRow, Note, Notice, Row, SegmentRow, Skeleton, Spinner, statusColor,
} from "./parts";
import type { GameDetail, UpscalerChoice, UpscalerJob, UpscalerStatus, UpscalersOverview, VerifyResult } from "./types";
import { upscalerErrorCode } from "./errorCode";

const INPUT_NAMES: Record<string, string> = { dlss: "DLSS", fsr31: "FSR 3.1", fsr2: "FSR 2", xess: "XeSS" };

const RETRYABLE = new Set(["download_failed", "hash_mismatch", "size_mismatch", "no_space", "helixsr_failed"]);

type Translate = (key: string, params?: Record<string, string | number>) => string;

function errorText(t: Translate, code: string | null | undefined): string {
  const key = `up.error.${code}`;
  const text = t(key);
  return text === key ? t("up.error.generic") : text;
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
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(draft?.advanced ?? false);
  const [choice, setChoice] = useState<UpscalerChoice>(() => draft?.choice ?? defaultChoice(overview.preferred));
  const keepDraft = useRef(!!draft);
  const changeChoice = (next: UpscalerChoice) => {
    setChoice(next);
    writeDraft(game.liveAppid, { choice: next, advanced });
  };
  const toggleAdvanced = () => {
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
  const [job, setJob] = useState<UpscalerJob | null>(overview.job?.appid === appid ? overview.job : null);
  const [message, setMessage] = useState<string | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [applied, setApplied] = useState<"now" | "restart" | "restarting" | null>(null);
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
  const mounted = useRef(true);
  const lastFacts = detail?.history.map((h) => h.facts).filter(Boolean).pop();
  const height = lastFacts?.resolution?.output[1] ?? overview.display?.[1] ?? 800;
  const backOverride = useMemo(() => ({ label: t("up.back"), onBack }), [t, onBack]);
  const borrowedBack = useSectionBack(backOverride);

  const load = useCallback(async () => {
    try {
      const hint = game.isNonSteam ? await readShortcutHint(game.liveAppid, game.name) : null;
      const next = await getUpscalersGame(appid, hint);
      if (!mounted.current) return;
      setDetail(next);
      setLoadError(null);
      if (next.install && !keepDraft.current) {
        setChoice(restoredChoice(next.install.build, next.install.options, overview.builds, overview.preferred));
      }
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
    if (next.state === "error") {
      const text = next.error === "no_space" && next.detail
        ? t("up.error.no_space", { mb: megabytes(Number(next.detail)) })
        : errorText(t, next.error);
      setMessage(next.detail && next.error?.startsWith("helixsr") ? `${text} (${next.detail})` : text);
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
      setMessage(errorText(t, upscalerErrorCode(error)));
    }
  };

  const install = detail?.install ?? null;
  const running = job?.state === "running";
  const builds = overview.builds;
  const status = install?.status ?? null;
  const sameBuild = install?.build === choice.build;
  const qualityChanged = install?.options.quality !== choice.quality;
  const modelChanged = (install?.options.model ?? null) !== (choice.model ?? null);
  const fgChanged = (install?.options.fg ?? "off") !== (choice.fg ?? "off")
    || (choice.fg === "on" && (install?.options.fg_route ?? null) !== (choice.fg_route ?? null));
  const dirty = !install || !sameBuild || qualityChanged || install.options.sharpness !== choice.sharpness || fgChanged || modelChanged;
  const routes = detail?.fg_plan?.routes ?? {};
  const route = choice.fg_route ?? (detail?.fg_plan?.route ?? detail?.fg_plan?.source ?? "game");
  const selected = builds.find((b) => b.id === choice.build);
  const selectedModels = selected?.models;
  const helix = selected?.engine === "helixsr";
  const replacesFsr = selected?.way === "fsr" || selected?.engine === "proton";
  const installedBuild = builds.find((b) => b.id === install?.build);
  const installedOptiscaler = !!install && installedBuild?.way !== "fsr" && installedBuild?.engine !== "proton";
  const installSelected = () => installUpscaler(appid, {
    ...choice, ...(replacesFsr ? { fg: "off" as const } : {}), confirm_anti_cheat: confirmAntiCheat,
    ...(selected?.engine === "proton" && protonEnv ? { env: protonEnv } : {}),
  });
  const reinstall = () => start(installSelected);
  const adoptAndInstall = async () => {
    if (foreignPending.current || running || gameRunning || !selected?.available || !selected.supported
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
    if (install && sameBuild) {
      setMessage(null);
      setApplied(null);
      try {
        const result = await configureUpscaler(appid, choice);
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

  const discard = () => {
    if (install) changeChoice(restoredChoice(install.build, install.options, builds, overview.preferred));
  };

  const askRestart = () => {
    holdPage();
    showModal(
      <ConfirmModal
        strTitle={t("up.restart.title")}
        strDescription={t("up.restart.body", { name: game.name })}
        strOKButtonText={t("up.restart.ok")}
        strCancelButtonText={t("up.bulk.cancel")}
        onOK={async () => {
          setApplied("restarting");
          const ok = await restartGame(game.liveAppid);
          if (!mounted.current) return;
          setApplied(null);
          if (!ok) setMessage(t("up.restart.failed"));
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
      // gamescope hands the key to the focused window: with the QAM open, Steam keeps it.
      holdPage();
      Navigation.CloseSideMenus();
      await pressUpscalerKey(appid, "fps_style");
    } catch {
      setCounterStyleFailed(true);
    }
  };

  const playing = !!install && gameRunning && !running;
  const [live, setGenerating] = useUpscalerLive(appid, playing, status === "pending" ? check : undefined);

  const facts = verify?.facts ?? detail?.history[detail.history.length - 1]?.facts;
  const render = facts?.resolution?.render[1] ?? null;
  const output = facts?.resolution?.output[1] ?? null;
  const blocked = foreignBusy || !detail?.analysis.target || !!detail.updating || (detail.analysis.foreign && !install)
    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat);
  const inputs = detail?.analysis.inputs ?? {};
  const blockedBuilds = builds.filter((b) => b.available && b.supported && buildBlocker(b, inputs, protonEnv));
  const amdMissing = !overview.gpu.startsWith("rdna") && builds.some((b) => b.available && !b.supported && b.family === "fsr");
  const coming = builds.filter((b) => !b.available && b.supported);
  const preferredBuild = builds.find((b) => b.id === overview.preferred && b.available);
  const runs = badgeLabel(installedBuild, install?.options.model, install?.build ?? "").full;
  const uses = [...new Set(Object.keys(inputs).map((k) => INPUT_NAMES[k]).filter(Boolean))];
  const qualityName = (q: UpscalerChoice["quality"]) => (q ? t(`up.quality.${q}`) : t("up.quality.game"));
  const changes = !install ? [] : [
    !sameBuild && t("up.change.version", { from: buildLabel(installedBuild ?? { family: "fsr", version: install.build }), to: selected ? buildLabel(selected) : choice.build }),
    qualityChanged && t("up.change.quality", { from: qualityName(install.options.quality), to: qualityName(choice.quality) }),
    modelChanged && t("up.change.model", { from: t(`up.model.${install.options.model ?? selectedModels?.[0] ?? "lite"}`), to: t(`up.model.${choice.model ?? selectedModels?.[0] ?? "lite"}`) }),
    fgChanged && t("up.change.fg", { from: fgName(t, install.options.fg, install.options.fg_route), to: fgName(t, choice.fg, choice.fg_route) }),
  ].filter((line): line is string => !!line);

  const subtitle = !detail ? null
    : detail.native ? null
    : playing ? t("up.sub.playing")
    : install ? runs
    : detail.analysis.foreign ? t("up.sub.foreign")
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
          {detail.native ? (
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
                : status === "active" ? undefined : t(`up.status.${status}`)}
              tone={status === "broken" ? "danger" : status === "loaded" ? "warn" : undefined}
            />
          ) : detail.analysis.foreign ? (
            <StatusLine icon={<LuArrowLeftRight size={17} />} title={t("up.foreign.title")} sub={t("up.foreign.body")} />
          ) : (
            <StatusLine
              title={t("up.state.none")}
            />
          )}
          {!detail.native && <ModelPicker builds={builds} choice={choice} inputs={inputs} protonEnv={protonEnv}
            disabled={running || foreignBusy} onChange={changeChoice} />}
          {wikiUpdating && (
            <span style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <Spinner size={10} /> {t("up.wiki.updating")}
            </span>
          )}
          {detail.recipe && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.recipe")}</span>}
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
          {detail.analysis.foreign && !install && (
            <Row><ActionButton label={t("up.foreign.adopt")} busy={foreignBusy} disabled={running || gameRunning || !selected?.available || !selected.supported || !detail.analysis.target || !!detail.updating || !!buildBlocker(selected, detail.analysis.inputs, protonEnv) || (detail.analysis.anti_cheat && !confirmAntiCheat)} onPress={() => void adoptAndInstall()} /></Row>
          )}
          {detail.foreign_backup && !install && !detail.analysis.foreign && (
            <Row><ActionButton label={t("up.foreign.restore")} disabled={foreignBusy || running || gameRunning} onPress={() => void foreignAction(restoreForeignUpscaler)} /></Row>
          )}
          {!detail.analysis.target && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.error.no_exe")}</Notice>}
          {detail.updating && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t(detail.updating === "running" ? "up.error.updating" : "up.error.update_pending")}</Notice>}
          {detail.analysis.target && uses.length === 0 && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.detect.noinputs")}</Notice>}
          {detail.recipe_info?.broken && <Notice icon={<LuTriangleAlert size={16} />} tone="warn">{t("up.recipe.broken")}</Notice>}
          {detail.recipe_info?.needs.map((need) => <Notice key={need} icon={<LuTriangleAlert size={16} />} tone="warn">{t(`up.recipe.need.${need}`)}</Notice>)}
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

      {detail && playing && !comparing && (
        <DuringPlay
          appid={appid}
          optiscaler={installedOptiscaler}
          fg={installedOptiscaler && install?.options.fg === "on"}
          live={live}
          onGenerating={setGenerating}
          onCompare={() => setComparing(true)}
        />
      )}
      {detail && install && comparing && (
        <CompareView appid={appid} gameRunning={gameRunning} onClose={() => setComparing(false)} />
      )}

      {detail && !detail.native && !replacesFsr && (
        <>
          <Label>{t("up.section.quality")}</Label>
          <SegmentRow
            value={choice.quality && QUALITIES.includes(choice.quality) ? choice.quality : null}
            onChange={(quality) => changeChoice({ ...choice, quality })}
            options={QUALITIES.map((q) => ({ value: q, label: t(`up.quality.${q}`), caption: `${renderHeight(height, q)}p` }))}
          />
        </>
      )}
      {detail && !detail.native && helix && <Note>{t("up.helix.pick.fsr")}</Note>}
      {detail && !detail.native && selected?.engine === "proton" && <Note>{t("up.proton.note")}</Note>}

      {detail && (
        <FrameGenRow
          appid={appid}
          liveAppid={game.liveAppid}
          isNonSteam={game.isNonSteam}
          gameRunning={gameRunning}
          routes={detail.native || !detail.fg_plan || replacesFsr ? {} : routes}
          inputs={detail.native ? {} : inputs}
          optiscaler={{ fg: choice.fg ?? "off", route }}
          installedRoute={install?.options.fg === "on" ? install.options.fg_route ?? detail.fg_plan?.route ?? detail.fg_plan?.source ?? "game" : null}
          gpu={overview.gpu}
          onOptiscaler={(fg, fg_route) => changeChoice({ ...choice, fg, fg_route: fg_route ?? choice.fg_route ?? null })}
        />
      )}

      {detail && !detail.native && (
        <>
          <Fold label={t("up.advanced")} open={advanced} onToggle={toggleAdvanced} />
          {advanced && (
            <>
              <ListCard>
                {playing && installedOptiscaler && (
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
              {amdMissing && <Note>{t("up.build.amdOnly")}</Note>}
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

      {running && job && <Progress job={job} />}
      {running && <Row><ActionButton label={t("up.cancel")} onPress={async () => { await cancelUpscalersJob(); }} /></Row>}
      {message && <Note tone="warn">{message}</Note>}
      {applied === "now" && !message && <Note>{t("up.live.appliedNow")}</Note>}
      {applied === "restart" && !message && gameRunning && (
        <>
          <Note>{t("up.live.appliedNext")}</Note>
          <Row><ActionButton label={t("up.restart.button")} onPress={askRestart} /></Row>
        </>
      )}
      {applied === "restarting" && <Note>{t("up.restart.doing")}</Note>}
      {!running && job?.state === "error" && job.kind === "install" && RETRYABLE.has(job.error ?? "") && (
        <Row><ActionButton label={t("up.retry")} onPress={reinstall} /></Row>
      )}

      {detail && !detail.native && !running && (status === "broken" || dirty) && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, paddingTop: theme.space.sm, borderTop: `1px solid ${theme.color.hairline}` }}>
          {status === "broken" ? (
            <Row><ActionButton primary label={t("up.repair")} onPress={reinstall} disabled={blocked} /></Row>
          ) : !install ? (
            <Row>
              <ActionButton primary label={t("up.activate", { name: selected ? buildLabel(selected) : choice.build })} onPress={apply} disabled={blocked} />
            </Row>
          ) : (
            <>
              {changes.map((line) => (
                <span key={line} style={{ fontSize: theme.font.caption + 1, color: theme.color.textMuted, textAlign: "center" }}>{line}</span>
              ))}
              <Row>
                <ActionButton label={t("up.discard")} onPress={discard} />
                <ActionButton primary label={t("up.save")} onPress={apply} disabled={blocked} />
              </Row>
            </>
          )}
        </div>
      )}
    </Focusable>
  );
};

function fgName(t: Translate, fg: "on" | "off" | undefined, route: string | null | undefined): string {
  if (fg !== "on") return t("up.fg.pick.off");
  return t(route === "optiscaler" ? "up.fg.pick.optiscaler" : "up.fg.pick.game");
}

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

const Progress: FC<{ job: UpscalerJob }> = ({ job }) => {
  const { t } = useI18n();
  const determinate = job.phase === "download" && job.total > 0;
  const ratio = determinate ? Math.min(1, job.done / job.total) : 0;
  const sample = useRef<PaceSample | null>(null);
  const [pace, setPace] = useState<{ rate: number; eta: number | null } | null>(null);
  useEffect(() => {
    if (job.phase !== "download") return;
    const now = { done: job.done, at: Date.now() };
    if (sample.current && now.at - sample.current.at >= 900) {
      setPace((last) => downloadPace(sample.current!, now, job.total, last?.rate ?? 0));
      sample.current = now;
    } else if (!sample.current) {
      sample.current = now;
    }
  }, [job.phase, job.done, job.total]);
  const label = job.phase === "download"
    ? t("up.phase.download", { done: megabytes(job.done), total: megabytes(job.total) })
    : t(`up.phase.${job.phase}`);
  const step = job.phase === "download" && pace
      ? pace.rate < 1024 ? t("up.phase.stalled")
      : t(pace.eta !== null && pace.eta < 3600 ? "up.phase.pace" : "up.phase.rate", {
        rate: (pace.rate / (1024 * 1024)).toFixed(1), eta: formatEta(pace.eta ?? 0),
      })
      : null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption + 1 }}>
        <Spinner size={12} /> {label}
      </div>
      {step && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{step}</span>}
      <div style={{ height: 4, borderRadius: 2, background: theme.color.hairline, overflow: "hidden" }}>
        <div
          data-pdc-up-motion
          style={{
            height: "100%", width: determinate ? `${ratio * 100}%` : "35%", background: theme.color.accent,
            transition: "width 200ms linear", animation: determinate ? "none" : "pdc-up-shimmer 1.2s ease-in-out infinite",
          }}
        />
      </div>
    </div>
  );
};

function formatEta(seconds: number): string {
  return seconds < 60 ? `${seconds} s` : `${Math.ceil(seconds / 60)} min`;
}
