import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState, type FC } from "react";
import { LuGauge, LuScale, LuSparkles } from "react-icons/lu";

import {
  cancelUpscalersJob, configureUpscaler, getUpscalersGame, getUpscalersJob, installUpscaler,
  setUpscalersExe, uninstallUpscaler, verifyUpscaler,
} from "../api";
import { CompactBackAction } from "../components/CompactBackAction";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import type { GameEntry } from "../launch/steamApi";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { theme } from "../theme";
import {
  EASY_MODES, QUALITIES, SHARPNESS, buildLabel, easyChoice, easyModeOf, megabytes, renderHeight,
  withOverride, withoutOverride,
} from "./model";
import { ActionButton, ChoiceCard, Dot, Label, Pips, Row, Skeleton, Spinner, statusColor } from "./parts";
import type { EasyMode, GameDetail, UpscalerChoice, UpscalerJob, UpscalersOverview, VerifyResult } from "./types";

const EASY_ICONS: Record<EasyMode, FC<{ size?: number }>> = { image: LuSparkles, balanced: LuScale, fps: LuGauge };
const POLL_MS = 250;
const INPUT_LABELS: Record<string, string> = { fsr31: "FSR 3.1", fsr2: "FSR 2", dlss: "DLSS", xess: "XeSS", streamline: "Streamline" };

function outputHeight(): number {
  const height = Math.round((window.screen?.height || 800) * (window.devicePixelRatio || 1));
  return height > 0 ? height : 800;
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
  const height = useMemo(outputHeight, []);

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
      setMessage(t(`up.error.${finished.error}`) === `up.error.${finished.error}` ? t("up.error.generic") : t(`up.error.${finished.error}`));
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
      const code = String((error as Error)?.message ?? "");
      setMessage(t(`up.error.${code}`) === `up.error.${code}` ? t("up.error.generic") : t(`up.error.${code}`));
    }
  };

  const install = detail?.install ?? null;
  const running = job?.state === "running";
  const builds = overview.builds;
  const sameBuild = install?.build === choice.build;
  const dirty = !install || !sameBuild || install.options.quality !== choice.quality || install.options.sharpness !== choice.sharpness;

  const apply = async () => {
    if (install && sameBuild) {
      setMessage(null);
      try {
        await configureUpscaler(appid, choice);
        await load();
        onChanged();
      } catch (error) {
        const code = String((error as Error)?.message ?? "");
        setMessage(t(`up.error.${code}`) === `up.error.${code}` ? t("up.error.generic") : t(`up.error.${code}`));
      }
      return;
    }
    await start(() => installUpscaler(appid, { ...choice, confirm_anti_cheat: confirmAntiCheat }));
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
    const start = detail?.analysis.target ?? "/home";
    try {
      const picked = await openFilePicker(0 as never, start, true, true, undefined, ["exe"]);
      if (picked?.realpath) setDetail(await setUpscalersExe(appid, picked.realpath));
    } catch (error) {
      const code = String((error as Error)?.message ?? "");
      if (code) setMessage(t("up.error.invalid_exe"));
    }
  };

  const status = install?.status ?? null;
  const facts = verify?.facts ?? detail?.history[detail.history.length - 1]?.facts;
  const resolution = facts?.resolution
    ? `${facts.resolution.render[1]}p → ${facts.resolution.output[1]}p`
    : choice.quality ? `${renderHeight(height, choice.quality)}p → ${height}p` : null;

  return (
    <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <CompactBackAction onBack={onBack} label={t("up.title")} />

      <div style={{ display: "flex", gap: theme.space.md, alignItems: "center", animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
        <GameCover urls={game.coverUrls} name={game.name} width={52} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: theme.font.body + 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {game.name}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {detail ? (
              <>
                <Dot color={statusColor(status)} />
                <span style={{ color: status ? theme.color.textPrimary : theme.color.textMuted }}>
                  {install ? `${buildLabel(builds.find((b) => b.id === install.build) ?? { family: "fsr", version: "" })} · ${t(`up.status.${status}`)}` : t("up.status.none")}
                </span>
              </>
            ) : <Skeleton height={10} width="60%" />}
          </div>
          {install && resolution && (
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{facts?.upscaler ? `${facts.upscaler} · ` : ""}{resolution}</div>
          )}
        </div>
        {install && !running && (
          <div style={{ width: 96 }}>
            <ActionButton label={t("up.verify")} onPress={check} busy={verifying} />
          </div>
        )}
      </div>

      {install?.status === "pending" && !verify && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.next.play")}</div>
      )}

      {!detail && !loadError && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, marginTop: theme.space.sm }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <Spinner size={12} /> {t("up.detect.analyzing")}
          </div>
          <Skeleton height={54} />
          <Skeleton height={54} />
        </div>
      )}
      {loadError && <ActionButton label={t("load.retry")} onPress={() => void load()} />}

      {detail && (
        <>
          <Row>
            {(["easy", "custom"] as const).map((m) => (
              <ChoiceCard key={m} selected={mode === m} onPick={() => setMode(m)} style={{ alignItems: "center", padding: theme.space.xs }}>
                <span style={{ fontWeight: 600, fontSize: theme.font.body }}>{t(`up.mode.${m}`)}</span>
              </ChoiceCard>
            ))}
          </Row>

          {mode === "easy" ? (
            <>
              <Label>{t("up.easy.title")}</Label>
              <Row>
                {EASY_MODES.map((m) => {
                  const Icon = EASY_ICONS[m];
                  const preset = easyChoice(m, overview.preferred);
                  return (
                    <ChoiceCard key={m} selected={easyModeOf(choice, overview.preferred) === m} onPick={() => setChoice(preset)}
                      style={{ alignItems: "center", textAlign: "center", padding: `${theme.space.md}px ${theme.space.xs}px` }}>
                      <Icon size={22} />
                      <span style={{ fontWeight: 600, fontSize: theme.font.body }}>{t(`up.easy.${m}`)}</span>
                      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                        {renderHeight(height, preset.quality!)}p
                      </span>
                    </ChoiceCard>
                  );
                })}
              </Row>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
                {buildLabel(builds.find((b) => b.id === overview.preferred) ?? { family: "fsr", version: "" })}
              </div>
            </>
          ) : (
            <>
              <Label>{t("up.section.version")}</Label>
              <Row>
                {builds.map((build) => {
                  const usable = build.available && build.supported;
                  return (
                    <ChoiceCard key={build.id} selected={choice.build === build.id} disabled={!usable}
                      onPick={() => setChoice({ ...choice, build: build.id })}>
                      <span style={{ fontWeight: 700, fontSize: theme.font.body }}>{buildLabel(build)}</span>
                      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                        {!build.available ? t("up.build.soon")
                          : !build.supported ? t("up.build.unsupported")
                          : build.id === overview.preferred ? t("up.build.recommended") : " "}
                      </span>
                      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                        <Pips value={build.image} glyph="★" /> <Pips value={build.cost} glyph="●" />
                      </span>
                    </ChoiceCard>
                  );
                })}
              </Row>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: 2 }}>
                ★ {t("up.image")} · ● {t("up.cost")}
              </div>

              <Label>{t("up.section.quality")}</Label>
              <Row>
                {QUALITIES.map((q) => (
                  <ChoiceCard key={q} selected={choice.quality === q} onPick={() => setChoice({ ...choice, quality: q })} style={{ alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: theme.font.caption + 1 }}>{t(`up.quality.${q}`)}</span>
                    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{renderHeight(height, q)}p</span>
                  </ChoiceCard>
                ))}
              </Row>

              <Label>{t("up.section.sharpness")}</Label>
              <Row>
                {SHARPNESS.map((s) => (
                  <ChoiceCard key={s} selected={choice.sharpness === s} onPick={() => setChoice({ ...choice, sharpness: s })} style={{ alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: theme.font.caption + 1 }}>{t(`up.sharp.${s}`)}</span>
                  </ChoiceCard>
                ))}
              </Row>
            </>
          )}

          <Label>{t("up.detect.title")}</Label>
          <div style={{ ...theme.card, padding: theme.space.sm, display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.caption }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: theme.space.sm }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {detail.analysis.exe ?? t("up.error.no_exe")}
                {detail.analysis.apis.length > 0 && <span style={{ color: theme.color.textMuted }}> · {detail.analysis.apis.filter((a) => a !== "dxgi").map((a) => a.toUpperCase()).join(" ")}</span>}
                {detail.analysis.manual && <span style={{ color: theme.color.accent }}> · {t("up.detect.manual")}</span>}
              </span>
            </div>
            <span style={{ color: theme.color.textMuted }}>
              {Object.keys(detail.analysis.inputs).length
                ? t("up.detect.inputs", { list: Object.keys(detail.analysis.inputs).map((k) => INPUT_LABELS[k] ?? k).join(", ") })
                : t("up.detect.noinputs")}
            </span>
          </div>
          <Row>
            <ActionButton label={t("up.detect.pick")} onPress={pickExe} disabled={running} />
            {detail.analysis.manual && (
              <ActionButton label={t("up.detect.auto")} onPress={async () => setDetail(await setUpscalersExe(appid, null))} disabled={running} />
            )}
          </Row>

          {detail.updating && <Notice color={theme.color.warn} text={t("up.error.updating")} />}
          {detail.analysis.foreign && !install && <Notice color={theme.color.warn} text={t("up.error.foreign")} />}
          {detail.analysis.anti_cheat && !install && (
            <>
              <Notice color={theme.color.danger} text={t("up.error.anti_cheat")} />
              <ChoiceCard selected={confirmAntiCheat} onPick={() => setConfirmAntiCheat(!confirmAntiCheat)} style={{ flexDirection: "row", alignItems: "center", gap: theme.space.xs }}>
                <span style={{ fontSize: theme.font.caption + 1 }}>{t("up.error.anti_cheat.confirm")}</span>
              </ChoiceCard>
            </>
          )}

          {running && job && <Progress job={job} />}
          {message && <Notice color={theme.color.warn} text={message} />}

          <div style={{ display: "flex", gap: theme.space.xs, marginTop: theme.space.sm }}>
            {running ? (
              <ActionButton label={t("up.cancel")} onPress={async () => { await cancelUpscalersJob(); }} />
            ) : (
              <>
                <ActionButton
                  primary
                  label={install ? (sameBuild ? t("up.save") : t("up.apply")) : t("up.apply")}
                  onPress={apply}
                  disabled={!dirty || !detail.analysis.target || detail.updating || (detail.analysis.foreign && !install)
                    || (detail.analysis.anti_cheat && !install && !confirmAntiCheat)}
                />
                {install && <ActionButton danger label={t("up.remove")} onPress={() => start(() => uninstallUpscaler(appid))} />}
              </>
            )}
          </div>

          {detail.history.length > 0 && (
            <>
              <Label>{t("up.history")}</Label>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {[...detail.history].reverse().slice(0, 6).map((entry) => {
                  const build = builds.find((b) => b.id === entry.build);
                  return (
                    <div key={`${entry.at}`} style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption }}>
                      <Dot color={statusColor(entry.result)} />
                      <span style={{ flex: 1, textDecoration: entry.result === "loaded" ? "line-through" : "none" }}>
                        {build ? buildLabel(build) : entry.build} · {entry.proxy}
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

const Notice: FC<{ color: string; text: string }> = ({ color, text }) => (
  <div style={{ display: "flex", gap: theme.space.xs, alignItems: "flex-start", fontSize: theme.font.caption + 1, padding: `${theme.space.xs}px 0` }}>
    <span style={{ marginTop: 5 }}><Dot color={color} /></span>
    <span>{text}</span>
  </div>
);

const Progress: FC<{ job: UpscalerJob }> = ({ job }) => {
  const { t } = useI18n();
  const determinate = job.phase === "download" && job.total > 0;
  const ratio = determinate ? Math.min(1, job.done / job.total) : 0;
  const label = job.phase === "download"
    ? t("up.phase.download", { done: megabytes(job.done), total: megabytes(job.total) })
    : t(`up.phase.${job.phase}`);
  return (
    <div style={{ ...theme.card, padding: theme.space.sm, display: "flex", flexDirection: "column", gap: theme.space.xs, animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
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
