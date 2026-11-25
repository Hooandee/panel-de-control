import { useEffect, useState, type FC } from "react";
import { LuTriangleAlert } from "react-icons/lu";
import { useI18n } from "../i18n";
import { readAppDetails } from "../launch/steamApi";
import { recordUiEvent } from "../system/uiEvents";
import { configuredLaunchTools } from "./launchTools";
import { Note } from "./parts";

export const LaunchMixNotice: FC<{ liveAppid: number; scaler: string | null }> = ({ liveAppid, scaler }) => {
  const { t } = useI18n();
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      const details = await readAppDetails(liveAppid).catch(() => null);
      if (alive) setNames(details ? configuredLaunchTools(details.launch) : []);
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 2500);
    return () => { alive = false; clearInterval(timer); };
  }, [liveAppid]);
  const combined = [...new Set([...(scaler ? [scaler] : []), ...names])];
  const combination = combined.join(", ");
  useEffect(() => {
    if (names.length && combined.length > 1) recordUiEvent("upscalers", "launch_mix", { appid: String(liveAppid), tools: combination });
  }, [liveAppid, combination]);
  if (!names.length || combined.length < 2) return null;
  return <Note><span style={{ display: "flex", alignItems: "center", gap: 6 }}><LuTriangleAlert size={14} style={{ flexShrink: 0 }} />{t("up.launch.mixed")}</span></Note>;
};
