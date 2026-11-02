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
import { theme } from "../theme";
import {
  EASY_MODES, QUALITIES, SHARPNESS, applyLaunch, buildLabel, easyChoice, easyModeOf, megabytes, renderHeight,
  revertLaunch,
} from "./model";
import { ActionButton, BAR_COLUMN, Bars, Chip, Dot, Label, Note, Row, SegmentRow, Skeleton, Spinner, statusColor } from "./parts";
import type { BuildInfo, EasyMode, GameDetail, UpscalerChoice, UpscalerJob, UpscalersOverview, VerifyResult } from "./types";

const POLL_MS = 250;
const INPUT_NAMES: Record<string, string> = { dlss: "DLSS", fsr31: "FSR", fsr2: "FSR", xess: "XeSS" };

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
  const [loadError, setLoadError] = useState(false);
  const [mode, setMode] = useState<"easy" | "custom">("easy");
  const [choice, setChoice] = useState<UpscalerChoice>(() => easyChoice("balanced", overview.preferred));
  const [job, setJob] = useState<UpscalerJob | null>(overview.job?.appid === appid ? overview.job : null);
  const [message, setMessage] = useState<string | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [confirmAntiCheat, setConfirmAntiCheat] = useState(false);
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
      setLoadError(false);
      if (next.install) {
        const restored: UpscalerChoice = { build: next.install.build, ...next.install.options };
        setChoice(restored);
        setMode(easyModeOf(restored, overview.preferred) ? "easy" : "custom");
      }
    } catch {
      if (mounted.current) setLoadError(true);
    }
  }, [appid, overview.preferred, game.isNonSteam, game.liveAppid, game.name]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const finish = useCallback(async (finished: UpscalerJob) => {
    const result = finished.result;
    if (finished.state === "done" && result?.overrides) {
      const details = await readAppDetails(game.liveAppid);
      const overrides = result.overrides;
      const args = result.args ?? [];
      if (finished.kind === "install") {
        const next = details ? applyLaunch(details.launch, overrides, args) : null;
        if (next && writeLaunchOptions(game.liveAppid, next.value, game.isNonSteam)) {
          if (next.added.length) await recordUpscalerArgs(appid, next.added).catch(() => undefined);
        } else {
          setMessage(t("up.launch.failed", { value: `WINEDLLOVERRIDES="${overrides.map((o) => o.split("=")[0]).join(",")}=n,b" %command% ${args.join(" ")}`.trim() }));
        }
      } else {
        const next = details ? revertLaunch(details.launch, overrides, args) : null;
        if (next === null || !writeLaunchOptions(game.liveAppid, next, game.isNonSteam)) setMessage(t("up.error.generic"));
        if (result.kept?.length) setMessage(t("up.kept", { count: result.kept.length }));
      }
    } else if (finished.state === "error") {
      setMessage(errorText(t, finished.error));
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
  const dirty = !install || !sameBuild || install.options.quality !== choice.quality || install.options.sharpness !== choice.sharpness;
  const reinstall = () => start(() => installUpscaler(appid, { ...choice, confirm_anti_cheat: confirmAntiCheat }));

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
    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat);
  const usable = builds.filter((b) => b.available && b.supported);
  const amdMissing = !overview.gpu.startsWith("rdna") && builds.some((b) => b.available && !b.supported && b.family === "fsr");
  const coming = builds.filter((b) => !b.available && b.supported);
  const preferredBuild = builds.find((b) => b.id === overview.preferred && b.available);
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
              {install ? t(`up.status.${status}`) : t("up.status.none")}
            </span>
            {install
              ? <Chip>{buildLabel(builds.find((b) => b.id === install.build) ?? { family: "fsr", version: "" })}</Chip>
              : preferredBuild && <Chip>{buildLabel(preferredBuild)}</Chip>}
          </div>
          {render && output && (
            <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textPrimary }}>{t("up.resolution", { render, output })}</span>
          )}
          {!install && preferredBuild && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.recommendedFor")}</span>
          )}
          {detail.recipe && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.recipe")}</span>}
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

      {detail && (
        <>
          {!detail.analysis.target && <Note tone="warn">{t("up.error.no_exe")}</Note>}
          {detail.updating && <Note tone="warn">{t(detail.updating === "running" ? "up.error.updating" : "up.error.update_pending")}</Note>}
          {detail.analysis.foreign && !install && <Note tone="warn">{t("up.error.foreign")}</Note>}
          {detail.analysis.target && compatible.length === 0 && <Note tone="warn">{t("up.detect.noinputs")}</Note>}
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
      {running && job && <Progress job={job} />}
      {message && <Note tone="warn">{message}</Note>}

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
      {loadError && <Row><ActionButton label={t("load.retry")} onPress={() => void load()} /></Row>}

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
              onChange={(m) => setChoice(easyChoice(m, overview.preferred))}
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
                onChange={(build) => setChoice({ ...choice, build })}
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
              {amdMissing && <Note>{t("up.build.amdOnly")}</Note>}
              {coming.map((b) => <Note key={b.id}>{t("up.build.soonLine", { name: buildLabel(b) })}</Note>)}

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
  const label = job.phase === "download"
    ? t("up.phase.download", { done: megabytes(job.done), total: megabytes(job.total) })
    : t(`up.phase.${job.phase}`);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption + 1 }}>
        <Spinner size={12} /> {label}
      </div>
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
