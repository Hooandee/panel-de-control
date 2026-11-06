import { useEffect, useRef, useState, type FC } from "react";
import { LuArrowLeftRight, LuLayers, LuTriangleAlert } from "react-icons/lu";

import {
  adoptForeignLsfg, getLsfgStatus, installLsfg, restoreForeignLsfg, setLsfgGame, type LsfgProfile, type LsfgStatus,
} from "../api";
import { ExperimentalBadge } from "../components/ExperimentalBadge";
import { useI18n } from "../i18n";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { theme } from "../theme";
import { readLosslessBranch, switchLosslessBranch, type LosslessBranchState } from "./losslessBranch";
import { fgOffer, withEnv } from "./model";
import { ActionButton, Label, ListCard, ListRow, Notice, PickerButton, Row } from "./parts";
import type { FgRoute } from "./types";

const LAUNCH_ENV = ["ENABLE_GAMESCOPE_WSI", "LSFGVK_PROFILE"];
type Pick = "off" | FgRoute | "lsfg";
const MULTIPLIERS = [2, 3, 4, 5, 6] as const;
type Flow = LsfgProfile["flow"];

/** Frame generation where Panel de Control adds something: the game's own on another GPU, OptiScaler's, or Lossless Scaling. */
export const FrameGenRow: FC<{
  appid: string;
  liveAppid: number;
  isNonSteam: boolean;
  gameRunning: boolean;
  routes: Partial<Record<FgRoute, unknown>>;
  inputs: Record<string, unknown>;
  optiscaler: { fg: "on" | "off"; route: FgRoute };
  installedRoute: FgRoute | null;
  gpu: string;
  onOptiscaler: (fg: "on" | "off", route: FgRoute | null) => void;
}> = ({ appid, liveAppid, isNonSteam, gameRunning, routes, inputs, optiscaler, installedRoute, gpu, onOptiscaler }) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<LsfgStatus | null>(null);
  const [branch, setBranch] = useState<LosslessBranchState | null>(null);
  const branchAbort = useRef<AbortController | null>(null);
  const [requestedLossless, setRequestedLossless] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getLsfgStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const profile = status?.profiles[appid] ?? null;
  const lossless = !!status && status.lossless;
  const offer = fgOffer(routes, inputs, gpu, lossless || !!profile, installedRoute);
  const gameInput = (routes.game as { input?: string } | undefined)?.input;
  const dlssBridge = !offer.own && (gameInput === "dlssg" || gameInput === "nukems");
  const current: Pick = profile || requestedLossless ? "lsfg" : optiscaler.fg === "on" && offer.options.includes(optiscaler.route) ? optiscaler.route : "off";

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

  const saveLsfg = async (next: Partial<LsfgProfile> | null) => {
    const result = await setLsfgGame(appid, next);
    const details = await readAppDetails(liveAppid);
    const env = Object.fromEntries(LAUNCH_ENV.map((name) => [name, result.env[name] ?? null]));
    const launch = details ? withEnv(details.launch, env) : null;
    if (launch === null || !writeLaunchOptions(liveAppid, launch, isNonSteam)) setMessage(t("up.lsfg.launchFailed"));
    else if (gameRunning && !profile && next) setMessage(t("up.lsfg.restart"));
  };

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await work();
      setStatus(await getLsfgStatus());
    } catch {
      setMessage(t("up.error.generic"));
    } finally {
      setBusy(false);
    }
  };

  const enableLossless = async (ready: LsfgStatus | null) => {
    if (!ready?.installed) setStatus(await installLsfg());
    await saveLsfg({ multiplier: profile?.multiplier ?? 2, flow: profile?.flow ?? "balanced", performance: profile?.performance ?? true });
    onOptiscaler("off", null);
    setRequestedLossless(false);
  };

  const choose = (pick: Pick) => run(async () => {
    if (pick === "lsfg") {
      if (status?.foreign || !status?.dll) {
        setRequestedLossless(true);
        return;
      }
      await enableLossless(status);
      return;
    }
    setRequestedLossless(false);
    if (profile) await saveLsfg(null);
    onOptiscaler(pick === "off" ? "off" : "on", pick === "off" ? null : pick);
  });

  const needBranch = current === "lsfg" && !!status && status.lossless && !status.dll;
  const foreignBackup = !!status && !status.foreign && !!status.foreign_backup;
  if (!offer.own && offer.options.length === 0 && !profile && !status?.foreign && !foreignBackup && !needBranch) return null;

  const options: { value: Pick; label: string; caption?: string }[] = [
    { value: "off", label: t("up.fg.pick.off") },
    ...offer.options.map((o) => ({ value: o as Pick, label: t(`up.fg.pick.${o === "game" && !dlssBridge ? "optiscaler" : o}`), caption: o === "optiscaler" || (o === "game" && !dlssBridge) ? undefined : t(`up.fg.pick.${o}.caption`, { name: gpu === "intel" ? "XeSS FG" : "FSR FG" }) })),
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <Label>{t("up.fg.title")}</Label>
      {offer.options.length > 0 && (
        <PickerButton
          label={t("up.fg.title")}
          value={current}
          disabled={busy}
          onChange={(pick) => void choose(pick)}
          options={options}
          badge={current === "optiscaler" ? <ExperimentalBadge>{t("up.fg.experimental")}</ExperimentalBadge> : undefined}
        />
      )}
      {profile && (
        <ListCard>
            <PickerButton
              showLabel label={t("up.lsfg.multiplier")}
              value={String(profile.multiplier)}
              disabled={busy}
              options={MULTIPLIERS.map((m) => ({ value: String(m), label: `×${m}` }))}
              onChange={(m) => void run(() => saveLsfg({ ...profile, multiplier: Number(m) as LsfgProfile["multiplier"] }))}
            />
            <PickerButton
              showLabel label={t("up.lsfg.flow")}
              value={profile.flow}
              disabled={busy}
              options={(["quality", "balanced", "performance", "fastest"] as Flow[]).map((f) => ({ value: f, label: t(`up.lsfg.flow.${f}`) }))}
              onChange={(flow) => void run(() => saveLsfg({ ...profile, flow }))}
            />
          <ListRow label={t("up.lsfg.light")} caption={t("up.lsfg.lightHint")} on={profile.performance} disabled={busy}
            onPress={() => void run(() => saveLsfg({ ...profile, performance: !profile.performance }))} />
        </ListCard>
      )}
      {offer.own && <Notice icon={<LuLayers size={16} />}>{t("up.fg.own", { name: t(`up.fg.own.${offer.own}`) })}</Notice>}
      {current === "game" && dlssBridge && <Notice icon={<LuLayers size={16} />}>{t("up.fg.hint.dlss")}</Notice>}
      {current === "optiscaler" && <Notice icon={<LuTriangleAlert size={16} />}>{t("up.fg.hint.opti")}</Notice>}
      {current === "lsfg" && status?.foreign && (
        <>
          <Notice icon={<LuArrowLeftRight size={16} />}>{t("up.lsfg.foreign")}</Notice>
          <Row><ActionButton label={t("up.lsfg.adopt")} busy={busy} disabled={!status.dll} onPress={() => void run(async () => { const adopted = await adoptForeignLsfg(); setStatus(adopted); if (requestedLossless) await enableLossless(adopted); })} /></Row>
        </>
      )}
      {requestedLossless && !status?.foreign && !!status?.dll && (
        <ActionButton label={t("up.activate", { name: "Lossless Scaling" })} busy={busy} onPress={() => void run(() => enableLossless(status))} />
      )}
      {current === "lsfg" && foreignBackup && (
        <Row><ActionButton label={t("up.lsfg.restore")} busy={busy} onPress={() => void run(async () => {
          const restored = await restoreForeignLsfg();
          await clearLsfgLaunch(restored.cleared ?? []);
          setStatus(restored);
        })} /></Row>
      )}
      {current === "lsfg" && branch?.supported && branch.available && branch.selected !== null && branch.selected !== "lsfg-vk" && (
        <ActionButton label={t("up.lsfg.switchBranch")} busy={busy} onPress={() => void run(async () => {
          const next = await switchLosslessBranch(15000, branchAbort.current?.signal);
          setBranch(next);
          setMessage(t("up.lsfg.branchChanged"));
        })} />
      )}
      {(needBranch || (current === "lsfg" && branch?.selected !== null && branch?.selected !== undefined && branch.selected !== "lsfg-vk")) && <Notice icon={<LuTriangleAlert size={16} />}>{t(branch?.selected === "lsfg-vk" ? "up.lsfg.branchWaiting" : "up.lsfg.needBranch")}</Notice>}
      {message && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{message}</span>}
    </div>
  );
};

/** Steam shortcut ids sit above 2^31; regular Steam apps below. */
async function clearLsfgLaunch(appids: string[]) {
  for (const id of appids) {
    const live = Number(id);
    const details = await readAppDetails(live).catch(() => null);
    const launch = details ? withEnv(details.launch, Object.fromEntries(LAUNCH_ENV.map((name) => [name, null]))) : null;
    if (launch !== null) writeLaunchOptions(live, launch, live > 0x7fffffff);
  }
}
