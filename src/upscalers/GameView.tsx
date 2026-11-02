import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useRef, useState, type FC } from "react";
import { LuChevronLeft, LuGauge, LuScale, LuSparkles } from "react-icons/lu";

import {
  cancelUpscalersJob, configureUpscaler, getUpscalersGame, getUpscalersJob, installUpscaler,
  setUpscalersExe, uninstallUpscaler, verifyUpscaler,
} from "../api";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import type { GameEntry } from "../launch/steamApi";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { theme } from "../theme";
import {
  EASY_MODES, QUALITIES, SHARPNESS, buildLabel, easyChoice, easyModeOf, megabytes, renderHeight,
  withOverride, withoutOverride,
} from "./model";
import { ActionButton, Bars, Chip, Dot, Label, Note, Row, SegmentRow, Skeleton, Spinner, statusColor } from "./parts";
import type { BuildInfo, EasyMode, GameDetail, UpscalerChoice, UpscalerJob, UpscalersOverview, VerifyResult } from "./types";

const EASY_ICONS: Record<EasyMode, FC<{ size?: number }>> = { image: LuSparkles, balanced: LuScale, fps: LuGauge };
const POLL_MS = 250;
const INPUT_NAMES: Record<string, string> = { dlss: "DLSS", fsr31: "FSR", fsr2: "FSR", xess: "XeSS" };

type Translate = (key: string, params?: Record<string, string | number>) => string;

function joinNames(names: string[], and: string): string {
  return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} ${and} ${names[names.length - 1]}`;
}

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
  const mounted = useRef(true);
  const height = overview.display?.[1] ?? 800;

  const load = useCallback(async () => {
    try {
      const next = await getUpscalersGame(appid);
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
  }, [appid, overview.preferred]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const finish = useCallback(async (finished: UpscalerJob) => {
    const override = finished.result?.override;
    if (finished.state === "done" && override) {
      const details = await readAppDetails(game.liveAppid);
      const next = details && (finished.kind === "install"
        ? withOverride(details.launch, override)
        : withoutOverride(details.launch, override));
      if (next === null || next === undefined || !writeLaunchOptions(game.liveAppid, next, game.isNonSteam)) {
        setMessage(t("up.launch.failed", { value: `WINEDLLOVERRIDES="${override}"` }));
      }
      if (finished.kind === "uninstall" && finished.result?.kept?.length) {
        setMessage(t("up.kept", { count: finished.result.kept.length }));
      }
    } else if (finished.state === "error") {
      setMessage(errorText(t, finished.error));
    }
    await load();
    onChanged();
  }, [game.liveAppid, game.isNonSteam, load, onChanged, t]);

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
  const render = facts?.resolution?.render[1] ?? (choice.quality ? renderHeight(height, choice.quality) : null);
  const output = facts?.resolution?.output[1] ?? height;
  const blocked = !detail?.analysis.target || detail.updating || (detail.analysis.foreign && !install)
    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat);
  const usable = builds.filter((b) => b.available && b.supported);
  const amdMissing = !overview.gpu.startsWith("rdna") && builds.some((b) => b.available && !b.supported && b.family === "fsr");
  const coming = builds.filter((b) => !b.available);
  const compatible = [...new Set(Object.keys(detail?.analysis.inputs ?? {}).map((k) => INPUT_NAMES[k]).filter(Boolean))];

  return (
    <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <Row>
        <Focusable
          onActivate={onBack}
          onClick={onBack}
          style={{
            display: "inline-flex", alignItems: "center", gap: 2, padding: `${theme.space.xs}px ${theme.space.sm}px`,
            borderRadius: theme.radius.sm, fontSize: theme.font.caption + 1, color: theme.color.textPrimary, cursor: "pointer",
            boxShadow: `inset 0 0 0 1px ${theme.color.outline}`,
          }}
        >
          <LuChevronLeft size={14} /> {t("up.back")}
        </Focusable>
      </Row>

      <div style={{ display: "flex", gap: theme.space.md, alignItems: "center", animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
        <GameCover urls={game.coverUrls} name={game.name} width={56} />
        <div style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: 3 }}>
          <div style={{ fontWeight: 700, fontSize: theme.font.body + 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {game.name}
          </div>
          {detail ? (
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body }}>
              {install && <Chip>{buildLabel(builds.find((b) => b.id === install.build) ?? { family: "fsr", version: "" })}</Chip>}
              <Dot color={statusColor(status)} />
              <span>{install ? t(`up.status.${status}`) : t("up.status.none")}</span>
            </div>
          ) : <Skeleton height={12} width="55%" />}
          {render && (
            <div style={{ fontSize: theme.font.caption + 1, color: theme.color.textMuted }}>
              {t("up.resolution", { render, output })}
            </div>
          )}
        </div>
      </div>

      {install && (status === "loaded" || status === "pending" || status === "not_run") && (
        <Note color={theme.color.accent}>{t(status === "loaded" ? "up.hint.loaded" : "up.next.play")}</Note>
      )}

      {running && job && <Progress job={job} />}
      {message && <Note color={theme.color.warn}>{message}</Note>}

      {detail && !running && (
        <Row>
          {status === "broken" ? (
            <ActionButton primary label={t("up.repair")} onPress={reinstall} disabled={blocked} />
          ) : (
            dirty && <ActionButton primary label={install ? t("up.save") : t("up.apply")} onPress={apply} disabled={blocked} />
          )}
          {install && <ActionButton label={t("up.verify")} onPress={check} busy={verifying} grow={false} />}
          {install && <ActionButton danger label={t("up.remove")} onPress={() => start(() => uninstallUpscaler(appid))} grow={false} />}
        </Row>
      )}
      {running && <Row><ActionButton label={t("up.cancel")} onPress={async () => { await cancelUpscalersJob(); }} /></Row>}

      {!detail && !loadError && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <Spinner size={12} /> {t("up.detect.analyzing")}
          </div>
          <Skeleton height={44} />
          <Skeleton height={64} />
        </div>
      )}
      {loadError && <ActionButton label={t("load.retry")} onPress={() => void load()} />}

      {detail && (
        <>
          <SegmentRow
            value={mode}
            onChange={setMode}
            options={[{ value: "easy", label: t("up.mode.easy") }, { value: "custom", label: t("up.mode.custom") }]}
          />

          {mode === "easy" ? (
            <SegmentRow<EasyMode>
              value={easyModeOf(choice, overview.preferred)}
              onChange={(m) => setChoice(easyChoice(m, overview.preferred))}
              options={EASY_MODES.map((m) => {
                const Icon = EASY_ICONS[m];
                return { value: m, label: t(`up.easy.${m}`), caption: t(`up.easy.caption.${m}`), icon: <Icon size={20} /> };
              })}
            />
          ) : (
            <>
              <Label>{t("up.section.version")}</Label>
              <SegmentRow
                value={choice.build}
                onChange={(build) => setChoice({ ...choice, build })}
                options={usable.map((build: BuildInfo) => ({
                  value: build.id,
                  label: buildLabel(build),
                  caption: (
                    <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                      <Bars value={build.image} label={t("up.bar.image")} />
                      <Bars value={4 - build.cost} label={t("up.bar.perf")} />
                    </span>
                  ),
                }))}
              />
              {amdMissing && <Note>{t("up.build.amdOnly")}</Note>}
              {coming.map((b) => <Note key={b.id}>{t("up.build.soonLine", { name: buildLabel(b) })}</Note>)}

              <Label>{t("up.section.quality")}</Label>
              <Note>{t("up.quality.help")}</Note>
              <SegmentRow
                value={choice.quality}
                onChange={(quality) => setChoice({ ...choice, quality })}
                options={QUALITIES.map((q) => ({ value: q, label: t(`up.quality.${q}`), caption: `${renderHeight(height, q)}p` }))}
              />

              <Label>{t("up.section.sharpness")}</Label>
              <SegmentRow
                value={choice.sharpness}
                onChange={(sharpness) => setChoice({ ...choice, sharpness })}
                options={SHARPNESS.map((s) => ({ value: s, label: t(`up.sharp.${s}`) }))}
              />
            </>
          )}

          <Label>{t("up.detect.title")}</Label>
          <Note>
            {compatible.length ? t("up.detect.inputs", { list: joinNames(compatible, t("up.and")) }) : t("up.detect.noinputs")}
          </Note>
          {detail.analysis.manual && detail.analysis.exe && (
            <Note>{t("up.detect.manual", { exe: detail.analysis.exe.split("/").pop() ?? detail.analysis.exe })}</Note>
          )}
          {!detail.analysis.target && <Note color={theme.color.warn}>{t("up.error.no_exe")}</Note>}
          {detail.updating && <Note color={theme.color.warn}>{t("up.error.updating")}</Note>}
          {detail.analysis.foreign && !install && <Note color={theme.color.warn}>{t("up.error.foreign")}</Note>}
          {detail.analysis.anti_cheat && !install && (
            <>
              <Note color={theme.color.danger}>{t("up.error.anti_cheat")}</Note>
              <SegmentRow
                value={confirmAntiCheat ? "yes" : null}
                onChange={() => setConfirmAntiCheat(!confirmAntiCheat)}
                options={[{ value: "yes", label: t("up.error.anti_cheat.confirm") }]}
              />
            </>
          )}
          <Row>
            <ActionButton label={t("up.detect.pick")} onPress={pickExe} disabled={running} />
            {detail.analysis.manual && (
              <ActionButton label={t("up.detect.auto")} onPress={async () => setDetail(await setUpscalersExe(appid, null))} disabled={running} />
            )}
          </Row>

          {detail.history.length > 0 && (
            <>
              <Label>{t("up.history")}</Label>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {[...detail.history].reverse().slice(0, 6).map((entry) => {
                  const build = builds.find((b) => b.id === entry.build);
                  return (
                    <div key={`${entry.at}`} style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption + 1 }}>
                      <Dot color={statusColor(entry.result)} />
                      <span style={{ flex: 1, textDecoration: entry.result === "loaded" ? "line-through" : "none" }}>
                        {build ? buildLabel(build) : entry.build}
                      </span>
                      <span style={{ color: theme.color.textMuted }}>{t(`up.status.${entry.result}`)}</span>
                    </div>
                  );
                })}
              </div>
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
