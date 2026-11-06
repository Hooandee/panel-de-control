import { useEffect, useState } from "react";
import { getLsfgStatus, getUpscalerLive, type LsfgProfile } from "../api";

type Live = Awaited<ReturnType<typeof getUpscalerLive>>;
export function useOverlayLive(appid: string | null, optiscaler: boolean) {
  const [state, setState] = useState<{ live: Live | null; lossless: LsfgProfile | null }>({ live: null, lossless: null });
  useEffect(() => {
    setState({ live: null, lossless: null });
    if (!appid) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let expiry: ReturnType<typeof setTimeout>;
    const read = async () => {
      expiry = setTimeout(() => { if (alive) setState({ live: null, lossless: null }); }, 5000);
      const [live, lossless] = await Promise.all([
        optiscaler ? getUpscalerLive(appid).catch(() => null) : Promise.resolve(null),
        getLsfgStatus().catch(() => null),
      ]);
      clearTimeout(expiry);
      if (!alive) return;
      setState({ live: live?.result === "active" ? live : null, lossless: lossless?.profiles[appid] ?? null });
      timer = setTimeout(read, 1500);
    };
    void read();
    return () => { alive = false; clearTimeout(timer); clearTimeout(expiry); };
  }, [appid, optiscaler]);
  return state;
}
