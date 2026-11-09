import { useEffect, useState } from "react";
import { getLsfgStatus, getMakoRuntime, getUpscalerLive, type LsfgProfile } from "../api";

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
  const [makoSpatial, setMakoSpatial] = useState<NonNullable<Awaited<ReturnType<typeof getMakoRuntime>>["spatial_resolution"]> | null>(null);
  const [makoMultiplier, setMakoMultiplier] = useState<number | null>(null);
  const [makoResolutionWarning, setMakoResolutionWarning] = useState(false);
  useEffect(() => {
    setMakoResolutionWarning(false);
    setMakoMultiplier(null);
    setMakoSpatial(null);
    if (!appid) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let expiry: ReturnType<typeof setTimeout>;
    const read = async () => {
      let expired = false;
      expiry = setTimeout(() => {
        expired = true;
        if (alive) { setMakoResolutionWarning(false); setMakoMultiplier(null); setMakoSpatial(null); }
      }, 5000);
      const mako = await getMakoRuntime(appid).catch(() => null);
      clearTimeout(expiry);
      if (!alive) return;
      if (expired) {
        timer = setTimeout(read, 1500);
        return;
      }
      const spatial = mako?.spatial_resolution;
      setMakoSpatial(mako?.observed === true && mako.scaling_active === true
        && mako.spatial_methods?.active_method === "mako"
        && mako.requested?.scaling_enabled === true && mako.applied?.scaling_enabled === true
        && !mako.error && !Object.values(mako.pending ?? {}).some(Boolean)
        && spatial && spatial.render?.length === 2 && spatial.output?.length === 2
        && [...spatial.render, ...spatial.output].every(value => Number.isInteger(value) && value > 0 && value <= 32768)
        ? spatial : null);
      const multiplier = mako?.applied?.multiplier;
      setMakoMultiplier(mako?.observed === true && mako.active === true
        && mako.role === "frame-generation" && mako.applied?.frame_generation_enabled === true
        && typeof multiplier === "number" && Number.isFinite(multiplier) && multiplier > 1
        && !mako.error && !Object.values(mako.pending ?? {}).some(Boolean) ? multiplier : null);
      setMakoResolutionWarning(mako?.observed === true && mako.scaling_active === false
        && mako.requested?.scaling_enabled === true && mako.applied?.scaling_enabled === true
        && mako.scaling_inactive_reason === "gamescope-presentation-target-no-headroom"
        && !mako.error && !Object.values(mako.pending ?? {}).some(Boolean));
      timer = setTimeout(read, 1500);
    };
    void read();
    return () => { alive = false; clearTimeout(timer); clearTimeout(expiry); };
  }, [appid]);
  return { ...state, makoResolutionWarning, makoMultiplier, makoSpatial };
}
