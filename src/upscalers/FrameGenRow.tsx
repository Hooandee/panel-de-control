import { Dropdown, Toggle } from "@decky/ui";
import { useEffect, useState, type FC, type ReactNode } from "react";
import { LuFeather, LuGauge, LuLayers } from "react-icons/lu";

import {
  adoptForeignLsfg, getLsfgStatus, installLsfg, restoreForeignLsfg, setLsfgGame, type LsfgProfile, type LsfgStatus,
} from "../api";
import { useI18n } from "../i18n";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { theme } from "../theme";
import { withEnv } from "./model";
import { ActionButton, Row } from "./parts";
import type { FgRoute } from "./types";

const LAUNCH_ENV = ["ENABLE_GAMESCOPE_WSI", "LSFGVK_PROFILE"];
type Pick = "off" | FgRoute | `lsfg-${LsfgProfile["multiplier"]}`;
const MULTIPLIERS = [2, 3, 4, 5, 6] as const;
type Flow = LsfgProfile["flow"];

/** One choice for every way to add frames: the game's own, OptiScaler's, or Lossless Scaling's. */
export const FrameGenRow: FC<{
  appid: string;
  liveAppid: number;
  isNonSteam: boolean;
  gameRunning: boolean;
  routes: Partial<Record<FgRoute, unknown>>;
  optiscaler: { fg: "on" | "off"; route: FgRoute };
  gameHint: string;
  onOptiscaler: (fg: "on" | "off", route: FgRoute | null) => void;
}> = ({ appid, liveAppid, isNonSteam, gameRunning, routes, optiscaler, gameHint, onOptiscaler }) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<LsfgStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getLsfgStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const profile = status?.profiles[appid] ?? null;
  const lossless = !!status && status.lossless && !!status.dll && !status.foreign;
  const current: Pick = profile ? `lsfg-${profile.multiplier}` as Pick : optiscaler.fg === "on" ? optiscaler.route : "off";

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

  const choose = (pick: Pick) => run(async () => {
    if (pick.startsWith("lsfg-")) {
      if (!status?.installed) setStatus(await installLsfg());
      await saveLsfg({ multiplier: Number(pick.slice(5)) as LsfgProfile["multiplier"], flow: profile?.flow ?? "balanced", performance: profile?.performance ?? true });
      onOptiscaler("off", null);
      return;
    }
    if (profile) await saveLsfg(null);
    onOptiscaler(pick === "off" ? "off" : "on", pick === "off" ? null : pick as FgRoute);
  });

  const options: { data: Pick; label: string }[] = [
    { data: "off", label: t("up.fg.pick.off") },
    ...("game" in routes ? [{ data: "game" as Pick, label: t("up.fg.pick.game") }] : []),
    ...("optiscaler" in routes ? [{ data: "optiscaler" as Pick, label: t("up.fg.pick.opti") }] : []),
    ...(lossless || profile ? MULTIPLIERS.map((m) => ({ data: `lsfg-${m}` as Pick, label: t("up.fg.pick.lsfg", { m }) })) : []),
  ];
  const hint = current === "game" ? gameHint : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <Line icon={<LuLayers size={16} />} label={t("up.fg.title")}>
        <Dropdown rgOptions={options} selectedOption={current} disabled={busy} onChange={(o) => void choose(o.data as Pick)} />
      </Line>
      {profile && (
        <Line icon={<LuGauge size={16} />} label={t("up.lsfg.flow")}>
          <Dropdown
            rgOptions={(["quality", "balanced", "performance", "fastest"] as Flow[]).map((f) => ({ data: f, label: t(`up.lsfg.flow.${f}`) }))}
            selectedOption={profile.flow}
            disabled={busy}
            onChange={(o) => void run(() => saveLsfg({ ...profile, flow: o.data as Flow }))}
          />
        </Line>
      )}
      {profile && (
        <Line icon={<LuFeather size={16} />} label={t("up.lsfg.light")}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Toggle value={profile.performance} disabled={busy} onChange={(on) => void run(() => saveLsfg({ ...profile, performance: on }))} />
          </div>
        </Line>
      )}
      {hint && <Hint>{hint}</Hint>}
      {status?.foreign && (
        <>
          <Hint>{t("up.lsfg.foreign")}</Hint>
          <Row><ActionButton label={t("up.foreign.adopt")} busy={busy} onPress={() => void run(async () => { setStatus(await adoptForeignLsfg()); })} /></Row>
        </>
      )}
      {status && !status.foreign && status.foreign_backup && (
        <Row><ActionButton label={t("up.foreign.restore")} busy={busy} onPress={() => void run(async () => { setStatus(await restoreForeignLsfg()); })} /></Row>
      )}
      {status && !status.foreign && (!status.lossless || !status.dll) && (
        <Hint>{t(!status.lossless ? "up.lsfg.needLossless" : "up.lsfg.needBranch")}</Hint>
      )}
      {message && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{message}</span>}
    </div>
  );
};

const Line: FC<{ icon: ReactNode; label: string; children: ReactNode }> = ({ icon, label, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
    <span style={{ display: "flex", color: theme.color.textMuted }}>{icon}</span>
    <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>{label}</span>
    <div style={{ minWidth: 150 }}>{children}</div>
  </div>
);

const Hint: FC<{ children: ReactNode }> = ({ children }) => (
  <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.35 }}>{children}</span>
);
