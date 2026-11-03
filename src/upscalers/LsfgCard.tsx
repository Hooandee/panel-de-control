import { useEffect, useState, type FC } from "react";

import { getLsfgStatus, installLsfg, setLsfgGame, type LsfgProfile, type LsfgStatus } from "../api";
import { useI18n } from "../i18n";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { theme } from "../theme";
import { withEnv } from "./model";
import { ActionButton, Label, Note, Row, SegmentRow, Skeleton } from "./parts";

const LAUNCH_ENV = ["ENABLE_GAMESCOPE_WSI", "LSFGVK_PROFILE"];
type Multiplier = "off" | "2" | "3" | "4";

/** Lossless Scaling frame generation through lsfg-vk: works on any Vulkan, DXVK or VKD3D game. */
export const LsfgCard: FC<{ appid: string; liveAppid: number; isNonSteam: boolean; gameRunning: boolean }> = ({
  appid, liveAppid, isNonSteam, gameRunning,
}) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<LsfgStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getLsfgStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  if (!status) return <Skeleton height={48} />;
  const profile = status.profiles[appid] ?? null;

  const save = async (next: Partial<LsfgProfile> | null) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await setLsfgGame(appid, next);
      const details = await readAppDetails(liveAppid);
      const env = Object.fromEntries(LAUNCH_ENV.map((name) => [name, result.env[name] ?? null]));
      const launch = details ? withEnv(details.launch, env) : null;
      if (launch === null || !writeLaunchOptions(liveAppid, launch, isNonSteam)) setMessage(t("up.lsfg.launchFailed"));
      else if (gameRunning && !profile && next) setMessage(t("up.lsfg.restart"));
      setStatus(await getLsfgStatus());
    } catch {
      setMessage(t("up.error.generic"));
    } finally {
      setBusy(false);
    }
  };

  const multiplier: Multiplier = profile ? (String(profile.multiplier) as Multiplier) : "off";

  return (
    <>
      <Label>{t("up.lsfg.title")}</Label>
      {status.foreign ? <Note>{t("up.lsfg.foreign")}</Note>
        : !status.lossless ? <Note>{t("up.lsfg.needLossless")}</Note>
        : !status.dll ? <Note>{t("up.lsfg.needBranch")}</Note>
        : !status.installed ? (
          <>
            <Note>{t("up.lsfg.explain")}</Note>
            <Row>
              <ActionButton label={t("up.lsfg.install")} busy={busy} onPress={async () => {
                setBusy(true);
                try { setStatus(await installLsfg()); } catch { setMessage(t("up.error.generic")); } finally { setBusy(false); }
              }} />
            </Row>
          </>
        ) : (
          <>
            <SegmentRow
              value={multiplier}
              onChange={(value) => save(value === "off" ? null : { ...profile, multiplier: Number(value) as 2 | 3 | 4 })}
              options={(["off", "2", "3", "4"] as Multiplier[]).map((m) => ({ value: m, label: m === "off" ? t("up.fg.off") : `${m}x` }))}
            />
            {profile && (
              <SegmentRow
                value={profile.flow}
                onChange={(flow) => save({ ...profile, flow })}
                options={(["quality", "balanced", "performance"] as const).map((f) => ({ value: f, label: t(`up.lsfg.flow.${f}`) }))}
              />
            )}
            <Note>{t(profile ? "up.lsfg.onNote" : "up.lsfg.explain")}</Note>
          </>
        )}
      {message && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{message}</span>}
    </>
  );
};
