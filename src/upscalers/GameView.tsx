import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState, type FC } from "react";

import {
  cancelUpscalersJob, configureUpscaler, getUpscalersGame, getUpscalersJob, installUpscaler,
  recordUpscalerArgs, setUpscalersExe, uninstallUpscaler, verifyUpscaler,
} from "../api";
import { CompactBackAction } from "../components/CompactBackAction";
import { GameCover } from "../components/GameCover";
import { useSectionBack } from "../components/sectionBack";
import { useRunningGame } from "../tdp/useRunningGame";
import { CompareView } from "./CompareView";
import { openIdentityModal } from "./IdentityModal";
import { readShortcutHint } from "./shortcutHint";
import { useI18n } from "../i18n";
import type { GameEntry } from "../launch/steamApi";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { CATALOG, pillVisible } from "../launch/catalog";
import type { GpuGen } from "../launch/proton";
import { useProtonCapabilities } from "../launch/useProtonCapabilities";
import { theme } from "../theme";
import {
  EASY_MODES, QUALITIES, SHARPNESS, buildLabel, easyChoice, easyModeOf, megabytes, renderHeight,
  buildBlocker, downloadPace, launchAfterJob, protonFsr4Env, type PaceSample,
} from "./model";
import { AdvancedIni } from "./AdvancedIni";
import { LivePanel } from "./LivePanel";
import { LsfgCard } from "./LsfgCard";
import { ActionButton, BAR_COLUMN, Bars, Chip, Dot, Label, Note, Row, SegmentRow, Skeleton, Spinner, statusColor } from "./parts";
import type { BuildInfo, EasyMode, FgRoute, GameDetail, UpscalerChoice, UpscalerJob, UpscalersOverview, VerifyResult } from "./types";

const POLL_MS = 250;
const INPUT_NAMES: Record<string, string> = { dlss: "DLSS", fsr31: "FSR", fsr2: "FSR", xess: "XeSS" };

const RETRYABLE = new Set(["download_failed", "hash_mismatch", "size_mismatch", "no_space", "helixsr_failed", "helixsr_build_failed"]);

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
}> = ({ game, overview, onBack, onChanged }) => {
  const { t } = useI18n();
  const appid = String(game.liveAppid);
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"easy" | "custom">("easy");
  const [choice, setChoice] = useState<UpscalerChoice>(() => easyChoice("balanced", overview.preferred));
  const [job, setJob] = useState<UpscalerJob | null>(overview.job?.appid === appid ? overview.job : null);
  const [message, setMessage] = useState<string | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [confirmAntiCheat, setConfirmAntiCheat] = useState(false);
  const [acceptNvidia, setAcceptNvidia] = useState(false);
  const [showBlocked, setShowBlocked] = useState(false);
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
  const [comparing, setComparing] = useState(false);
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
      if (next.install) {
        const restored: UpscalerChoice = { build: next.install.build, ...next.install.options };
        setChoice(restored);
        setMode(easyModeOf(restored, overview.preferred) ? "easy" : "custom");
      }
    } catch (error) {
      if (mounted.current) setLoadError(String((error as Error)?.message ?? "") || "generic");
    }
  }, [appid, overview.preferred, game.isNonSteam, game.liveAppid, game.name]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const finish = useCallback(async (finished: UpscalerJob) => {
    const result = finished.result;
    if (finished.state === "done" && result?.launcher) {
      if (result.kept?.length) setMessage(t("up.kept", { count: result.kept.length }));
    } else if (finished.state === "done" && result?.overrides) {
      const details = await readAppDetails(game.liveAppid);
      const overrides = result.overrides;
      const args = result.args ?? [];
      const next = details ? launchAfterJob(details.launch, result, finished.kind) : null;
      if (finished.kind === "install") {
        if (next && writeLaunchOptions(game.liveAppid, next.value, game.isNonSteam)) {
          if (next.added.length) await recordUpscalerArgs(appid, next.added).catch(() => undefined);
        } else {
          setMessage(t("up.launch.failed", { value: `WINEDLLOVERRIDES="${overrides.map((o) => o.split("=")[0]).join(",")}=n,b" %command% ${args.join(" ")}`.trim() }));
        }
      } else {
        if (next === null || !writeLaunchOptions(game.liveAppid, next.value, game.isNonSteam)) setMessage(t("up.error.generic"));
        if (result.kept?.length) setMessage(t("up.kept", { count: result.kept.length }));
      }
    } else if (finished.state === "error") {
      const text = finished.error === "no_space" && finished.detail
        ? t("up.error.no_space", { mb: megabytes(Number(finished.detail)) })
        : errorText(t, finished.error);
      setMessage(finished.detail && finished.error?.startsWith("helixsr") ? `${text} (${finished.detail})` : text);
    }
    await load();
    onChanged();
  }, [appid, game.liveAppid, game.isNonSteam, load, onChanged, t]);

  useEffect(() => {
    if (!job || job.state !== "running") return;
    const timer = window.setInterval(async () => {
      const next = await getUpscalersJob().catch(() => null);
      if (!mounted.current || !next || next.id !== job.id) return;
      setJob(next);
      if (next.state !== "running") {
        window.clearInterval(timer);
        void finish(next);
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.state, finish]);

  const start = async (run: () => Promise<UpscalerJob>) => {
    setMessage(null);
    setVerify(null);
    try {
      setJob(await run());
    } catch (error) {
      setMessage(errorText(t, String((error as Error)?.message ?? "")));
    }
  };

  const install = detail?.install ?? null;
  const running = job?.state === "running";
  const builds = overview.builds;
  const status = install?.status ?? null;
  const sameBuild = install?.build === choice.build;
  const dirty = !install || !sameBuild || install.options.quality !== choice.quality || install.options.sharpness !== choice.sharpness
    || (install.options.fg ?? "off") !== (choice.fg ?? "off")
    || (choice.fg === "on" && (install.options.fg_route ?? null) !== (choice.fg_route ?? null))
    || (install.options.model ?? null) !== (choice.model ?? null);
  const routes = detail?.fg_plan?.routes ?? {};
  const bothRoutes = "game" in routes && "optiscaler" in routes;
  const route: FgRoute = choice.fg_route ?? (detail?.fg_plan?.route ?? detail?.fg_plan?.source ?? "game");
  const gameFgInput = (detail?.fg_plan?.routes?.game as { input?: string } | undefined)?.input;
  const gameFgHint = [
    t(gameFgInput === "xefg" ? "up.fg.enableInGame.xess" : gameFgInput === "fsrfg" ? "up.fg.enableInGame.fsr" : "up.fg.enableInGame.dlss"),
    detail?.fg_note === "reflexOff" ? t("up.fg.note.reflexOff") : null,
  ].filter(Boolean).join(". ");
  const selected = builds.find((b) => b.id === choice.build);
  const selectedModels = selected?.models;
  const helix = selected?.engine === "helixsr";
  const replacesFsr = selected?.way === "fsr" || selected?.engine === "proton";
  const needsNvidia = selected?.way === "scaler" && install?.build !== selected.id;
  const installedBuild = builds.find((b) => b.id === install?.build);
  const reinstall = () => start(() => installUpscaler(appid, {
    ...choice, ...(replacesFsr ? { fg: "off" as const } : {}), confirm_anti_cheat: confirmAntiCheat, accept_nvidia: acceptNvidia,
    ...(selected?.engine === "proton" && protonEnv ? { env: protonEnv } : {}),
  }));

  const apply = async () => {
    if (install && sameBuild) {
      setMessage(null);
      try {
        await configureUpscaler(appid, choice);
        await load();
        onChanged();
      } catch (error) {
        setMessage(errorText(t, String((error as Error)?.message ?? "")));
      }
      return;
    }
    await reinstall();
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
    try {
      const picked = await openFilePicker(0 as never, detail?.analysis.target ?? "/home", true, true, undefined, ["exe"]);
      if (picked?.realpath) setDetail(await setUpscalersExe(appid, picked.realpath));
    } catch (error) {
      if (String((error as Error)?.message ?? "")) setMessage(t("up.error.invalid_exe"));
    }
  };

  const facts = verify?.facts ?? detail?.history[detail.history.length - 1]?.facts;
  const render = facts?.resolution?.render[1] ?? null;
  const output = facts?.resolution?.output[1] ?? null;
  const blocked = !detail?.analysis.target || !!detail.updating || (detail.analysis.foreign && !install)
    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat) || (needsNvidia && !acceptNvidia);
  const inputs = detail?.analysis.inputs ?? {};
  const usable = builds.filter((b) => b.available && b.supported && !buildBlocker(b, inputs, protonEnv));
  const blockedBuilds = builds.filter((b) => b.available && b.supported && buildBlocker(b, inputs, protonEnv));
  const amdMissing = !overview.gpu.startsWith("rdna") && builds.some((b) => b.available && !b.supported && b.family === "fsr");
  const coming = builds.filter((b) => !b.available && b.supported);
  const preferredBuild = builds.find((b) => b.id === overview.preferred && b.available);
  const shownBuild = install?.build ?? preferredBuild?.id;
  const tested = !!shownBuild && !!detail?.history.some((h) => h.build === shownBuild && h.result === "active");
  const does = selected?.engine === "proton" ? "up.does.proton" : selected?.way === "fsr" ? "up.does.fsr" : "up.does.optiscaler";
  const compatible = [...new Set(Object.keys(detail?.analysis.inputs ?? {}).map((k) => INPUT_NAMES[k]).filter(Boolean))];

  return (
    <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {!borrowedBack && <Row><CompactBackAction onBack={onBack} label={t("up.back")} /></Row>}

      <div style={{ display: "flex", gap: theme.space.sm, alignItems: "center", animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
        <GameCover urls={game.coverUrls} name={game.name} width={40} />
        <div style={{ fontWeight: 700, fontSize: theme.font.body + 1, lineHeight: 1.2, color: theme.color.textPrimary }}>{game.name}</div>
      </div>

      {detail ? (
        <div style={{
          ...theme.card,
          padding: `${theme.space.sm}px ${theme.space.md}px`,
          display: "flex", flexDirection: "column", gap: 4,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
            {install && <Dot color={statusColor(status)} />}
            <span style={{ flex: 1, fontWeight: 700, fontSize: theme.font.body, color: theme.color.textPrimary }}>
              {detail.native ? t("up.native.title") : install ? t(`up.status.${status}`) : t("up.status.none")}
            </span>
            {install
              ? <Chip>{buildLabel(builds.find((b) => b.id === install.build) ?? { family: "fsr", version: "" })}</Chip>
              : preferredBuild && !detail.native && <Chip>{buildLabel(preferredBuild)}</Chip>}
          </div>
          {tested && <span style={{ fontSize: theme.font.caption, color: theme.color.accent }}>{t("up.tested")}</span>}
          {install?.options.fg === "on" && facts?.fg && (
            <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textPrimary }}>{t("up.fg.active")}</span>
          )}
          {install?.options.fg === "on" && !facts?.fg && facts?.upscaler && detail.fg_plan?.source === "game" && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{gameFgHint}</span>
          )}
          {render && output && render < output && (
            <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs, color: theme.color.textPrimary }}>
              <span style={{ fontSize: theme.font.body + 6, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{render}p</span>
              <span style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>→</span>
              <span style={{ fontSize: theme.font.body + 6, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{output}p</span>
            </div>
          )}
          {!install && preferredBuild && !detail.native && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.recommendedFor")}</span>
          )}
          {detail.recipe && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.recipe")}</span>}
          {detail.launcher && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t(`up.launcher.${detail.launcher}`)}</span>}
          {detail.native && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.native")}</span>}
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
      ) : <Skeleton height={56} />}

      {detail && !detail.native && (
        <>
          {!detail.analysis.target && <Note tone="warn">{t("up.error.no_exe")}</Note>}
          {detail.updating && <Note tone="warn">{t(detail.updating === "running" ? "up.error.updating" : "up.error.update_pending")}</Note>}
          {detail.analysis.foreign && !install && <Note tone="warn">{t("up.error.foreign")}</Note>}
          {detail.analysis.target && compatible.length === 0 && <Note tone="warn">{t("up.detect.noinputs")}</Note>}
          {detail.recipe_info?.broken && <Note tone="warn">{t("up.recipe.broken")}</Note>}
          {detail.recipe_info?.needs.map((need) => <Note key={need} tone="warn">{t(`up.recipe.need.${need}`)}</Note>)}
          {detail.analysis.anti_cheat && !install && (
            <>
              <Note tone="danger">{t("up.error.anti_cheat")}</Note>
              <SegmentRow
                value={confirmAntiCheat ? "yes" : null}
                onChange={() => setConfirmAntiCheat(!confirmAntiCheat)}
                options={[{ value: "yes", label: t("up.error.anti_cheat.confirm") }]}
              />
            </>
          )}

        </>
      )}
      {detail && install && gameRunning && !running && (
        <LivePanel
          appid={appid}
          fg={install.options.fg === "on" && installedBuild?.way !== "fsr" && installedBuild?.engine !== "proton"}
          menu={installedBuild?.way !== "fsr" && installedBuild?.engine !== "proton"}
          onActive={status === "pending" ? check : undefined}
        />
      )}
      {running && job && <Progress job={job} />}
      {message && <Note tone="warn">{message}</Note>}
      {!running && job?.state === "error" && job.kind === "install" && RETRYABLE.has(job.error ?? "") && (
        <Row><ActionButton label={t("up.retry")} onPress={reinstall} /></Row>
      )}

      {detail && !detail.native && !running && (status === "broken" || dirty) && (
        <Row>
          <ActionButton
            primary
            label={status === "broken" ? t("up.repair") : install ? t("up.save") : t("up.apply")}
            onPress={status === "broken" ? reinstall : apply}
            disabled={blocked}
          />
        </Row>
      )}
      {detail && !detail.native && !running && (status === "broken" || dirty) && !sameBuild && (
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.35 }}>{t(does)}</span>
      )}
      {detail && !running && install && (
        <Row>
          <ActionButton label={t("up.verify")} onPress={check} busy={verifying} />
          <ActionButton danger label={t("up.remove")} onPress={() => start(() => uninstallUpscaler(appid))} />
        </Row>
      )}
      {detail && !running && install && !comparing && (
        <Row><ActionButton label={t("up.compare.open")} onPress={() => setComparing(true)} /></Row>
      )}
      {detail && install && comparing && (
        <CompareView appid={appid} gameRunning={gameRunning} onClose={() => setComparing(false)} />
      )}
      {detail?.native && <LsfgCard appid={appid} liveAppid={game.liveAppid} isNonSteam={game.isNonSteam} gameRunning={gameRunning} />}
      {running && <Row><ActionButton label={t("up.cancel")} onPress={async () => { await cancelUpscalersJob(); }} /></Row>}

      {!detail && !loadError && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <Spinner size={12} /> {t("up.detect.analyzing")}
          </div>
          <Skeleton height={36} />
          <Skeleton height={96} />
        </div>
      )}
      {loadError === "not_installed" && <Note tone="warn">{t("up.error.missingFolder")}</Note>}
      {loadError && loadError !== "not_installed" && <Row><ActionButton label={t("load.retry")} onPress={() => void load()} /></Row>}

      {detail && !detail.native && (
        <>
          <SegmentRow
            value={mode}
            onChange={setMode}
            options={[{ value: "easy", label: t("up.mode.easy") }, { value: "custom", label: t("up.mode.custom") }]}
          />

          {mode === "easy" ? (
            <SegmentRow<EasyMode>
              vertical
              value={easyModeOf(choice, overview.preferred)}
              onChange={(m) => setChoice(easyChoice(m, overview.preferred, choice.fg ?? "off"))}
              options={EASY_MODES.map((m) => ({ value: m, label: t(`up.easy.${m}`), caption: t(`up.easy.caption.${m}`) }))}
            />
          ) : (
            <>
              <Label aside={
                <span style={{ display: "inline-flex", paddingRight: theme.space.sm + 4 }}>
                  <span style={{ width: BAR_COLUMN, textAlign: "center" }}>{t("up.bar.image")}</span>
                  <span style={{ width: BAR_COLUMN, textAlign: "center" }}>{t("up.bar.perf")}</span>
                </span>
              }>{t("up.section.version")}</Label>
              <SegmentRow
                vertical
                value={choice.build}
                onChange={(build) => setChoice({ ...choice, build, model: null })}
                options={usable.map((build: BuildInfo) => ({
                  value: build.id,
                  label: buildLabel(build),
                  caption: (
                    <span style={{ display: "inline-flex" }}>
                      <Bars value={build.image} />
                      <Bars value={4 - build.cost} />
                    </span>
                  ),
                }))}
              />
              {(selectedModels?.length ?? 0) > 1 && (
                <>
                  <Label>{t("up.section.model")}</Label>
                  <SegmentRow
                    value={choice.model ?? selectedModels![0]}
                    onChange={(model) => setChoice({ ...choice, model })}
                    options={selectedModels!.map((m) => ({ value: m, label: t(`up.model.${m}`) }))}
                  />
                  <Note>{t("up.model.help")}</Note>
                </>
              )}
              {amdMissing && <Note>{t("up.build.amdOnly")}</Note>}
              {blockedBuilds.length > 0 && (
                <Row>
                  <ActionButton
                    label={showBlocked ? t("up.blocked.hide") : t("up.blocked.more", { count: blockedBuilds.length })}
                    onPress={() => setShowBlocked(!showBlocked)}
                  />
                </Row>
              )}
              {showBlocked && blockedBuilds.map((b) => (
                <Note key={b.id}>{t(buildBlocker(b, inputs, protonEnv) === "needsProton" ? "up.proton.needsProton" : "up.helix.needsFsr31", { name: buildLabel(b) })}</Note>
              ))}
              {coming.map((b) => <Note key={b.id}>{t("up.build.soonLine", { name: buildLabel(b) })}</Note>)}

              {helix && <Note>{t(selected?.way === "fsr" ? "up.helix.pick.fsr" : "up.helix.pick.dlss")}</Note>}
              {selected?.engine === "proton" && <Note>{t("up.proton.note")}</Note>}
              {!replacesFsr && (
                <>
                  <Label>{t("up.section.quality")}</Label>
                  <SegmentRow
                    vertical
                    value={choice.quality}
                    onChange={(quality) => setChoice({ ...choice, quality })}
                    options={QUALITIES.map((q) => ({ value: q, label: t(`up.quality.${q}`), caption: `${renderHeight(height, q)}p` }))}
                  />
                  <Note>{t("up.quality.help")}</Note>

                  <Label>{t("up.section.sharpness")}</Label>
                  <SegmentRow
                    value={choice.sharpness}
                    onChange={(sharpness) => setChoice({ ...choice, sharpness })}
                    options={SHARPNESS.map((s) => ({ value: s, label: t(`up.sharp.${s}`) }))}
                  />
                </>
              )}
            </>
          )}

          {needsNvidia && (
            <>
              <Note>{t("up.helix.nvidia")}</Note>
              <SegmentRow
                value={acceptNvidia ? "yes" : null}
                onChange={() => setAcceptNvidia(!acceptNvidia)}
                options={[{ value: "yes", label: t("up.helix.nvidia.accept") }]}
              />
            </>
          )}

          {detail.fg_plan && !replacesFsr && (
            <>
              <Label>{t("up.fg.title")}</Label>
              <SegmentRow
                value={choice.fg ?? "off"}
                onChange={(fg) => setChoice({ ...choice, fg })}
                options={[{ value: "off", label: t("up.fg.off") }, { value: "on", label: t("up.fg.on") }]}
              />
              <Note>{t("up.fg.explain")}</Note>
              {choice.fg === "on" && bothRoutes && (
                <SegmentRow
                  value={route}
                  onChange={(fg_route) => setChoice({ ...choice, fg_route })}
                  options={[{ value: "game", label: t("up.fg.route.game") }, { value: "optiscaler", label: t("up.fg.route.opti") }]}
                />
              )}
              <Note>{route === "game" ? `${t("up.fg.fromGame")}. ${gameFgHint}` : t(bothRoutes ? "up.fg.fromOptiChoice" : "up.fg.fromOpti")}</Note>
            </>
          )}

          <LsfgCard appid={appid} liveAppid={game.liveAppid} isNonSteam={game.isNonSteam} gameRunning={gameRunning} />

          {install && installedBuild?.way !== "fsr" && installedBuild?.engine !== "proton" && !running && <AdvancedIni appid={appid} />}

          {detail.analysis.manual && detail.analysis.exe && (
            <Note>{t("up.detect.manual", { exe: detail.analysis.exe.split("/").pop() ?? detail.analysis.exe })}</Note>
          )}
          <Row>
            {detail.analysis.manual
              ? <ActionButton label={t("up.detect.auto")} onPress={async () => setDetail(await setUpscalersExe(appid, null))} disabled={running} />
              : <ActionButton label={t("up.detect.pick")} onPress={pickExe} disabled={running} />}
          </Row>

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
    </Focusable>
  );
};

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
  const step = job.phase === "build" ? job.step
    : job.phase === "download" && pace
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
