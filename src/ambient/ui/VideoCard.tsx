import type { CSSProperties, FC } from "react";
import { LuHeart, LuMaximize, LuMinimize, LuMinimize2, LuPause, LuPlay, LuScaling, LuSkipForward } from "react-icons/lu";

import type { LibraryControl } from "./libraryDock";
import { useI18n } from "../../i18n";
import { Progress, RoundButton, TouchOnlyScope } from "./NowPlaying";

export const VIDEO_RADIUS_PX = 18;

const oneLine: CSSProperties = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

/**
 * The floating card when it holds video: the video fills it (drawn underneath by the video
 * frame) and the title and controls float on top, fading out after a few seconds.
 */
export const VideoCard: FC<{
  height: number;
  title: string;
  subtitle: string;
  busy: boolean;
  revealed: boolean;
  libraryFocus?: LibraryControl | null;
  onToggle: () => void;
  onNext?: () => void;
  onCollapse?: () => void;
  live: boolean;
  fraction: number;
  onSeek: (fraction: number) => void;
  onResize?: () => void;
  fullscreen?: boolean;
  onFullscreen?: () => void;
  favorite?: boolean;
  onFavorite?: () => void;
}> = ({ height, title, subtitle, busy, revealed, libraryFocus, onToggle, onNext, onCollapse, live, fraction, onSeek, onResize, fullscreen, onFullscreen, favorite, onFavorite }) => {
  const { t } = useI18n();
  const inLibrary = libraryFocus !== undefined;
  return (
    <TouchOnlyScope>
      <div style={{ position: "relative", height, borderRadius: fullscreen ? 0 : VIDEO_RADIUS_PX, overflow: "hidden", boxShadow: "0 12px 32px rgba(0,0,0,0.45)", color: "#fff" }}>
        <div style={{ position: "absolute", inset: 0, opacity: revealed ? 1 : 0, transition: "opacity 260ms ease", pointerEvents: revealed ? "auto" : "none" }}>
          <div style={{ position: "absolute", top: 8, right: 8, display: "flex", gap: 8 }}>
            {onFavorite && (
              <RoundButton glass label={favorite ? t("ambient.stations.unfavorite") : t("ambient.stations.favorite")} onActivate={onFavorite} active={favorite} size={36}>
                <LuHeart size={15} fill={favorite ? "currentColor" : "none"} />
              </RoundButton>
            )}
            {onResize && <RoundButton glass label={t("ambient.overlay.videoSize")} onActivate={onResize} size={36}>
              <LuScaling size={15} />
            </RoundButton>}
            {onCollapse && <RoundButton glass label={t("ambient.player.hideVideo")} onActivate={onCollapse} size={36}>
              <LuMinimize2 size={15} />
            </RoundButton>}
            {onFullscreen && <RoundButton glass label={t(fullscreen ? "ambient.player.exitFullscreen" : "ambient.player.fullscreen")} onActivate={onFullscreen} size={36}>
              {fullscreen ? <LuMinimize size={15} /> : <LuMaximize size={15} />}
            </RoundButton>}
          </div>
          <div style={{ position: inLibrary ? "static" : "absolute", left: 0, right: 0, bottom: 0, padding: inLibrary ? 0 : "28px 12px 8px", display: "flex", flexDirection: "column", gap: 4, background: "linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,0.72))" }}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            <div style={{ position: inLibrary ? "absolute" : undefined, top: inLibrary ? 6 : undefined, left: inLibrary ? 12 : undefined, right: inLibrary ? 12 : undefined, display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
              <span style={{ ...oneLine, fontSize: 13, fontWeight: 700, textShadow: "0 1px 6px rgba(0,0,0,0.6)" }}>{title}</span>
              {subtitle && !inLibrary && <span style={{ ...oneLine, fontSize: 11, color: "rgba(255,255,255,0.78)" }}>{subtitle}</span>}
            </div>
            <div data-video-control="toggle" style={inLibrary ? { position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", borderRadius: "50%", boxShadow: libraryFocus === "toggle" ? "0 0 0 2px #fff" : "none" } : undefined}>
            <RoundButton glass primary label={busy ? t("ambient.player.pause") : t("ambient.player.play")} onActivate={onToggle} size={42}>
              {busy ? <LuPause size={16} /> : <LuPlay size={16} style={{ marginLeft: 2 }} />}
            </RoundButton>
            </div>
            {onNext && (
              <RoundButton glass label={t("ambient.player.next")} onActivate={onNext} size={36}>
                <LuSkipForward size={14} />
              </RoundButton>
            )}
          </div>
          <div data-video-control="progress" style={inLibrary ? { position: "absolute", left: 12, right: 12, bottom: 8, borderRadius: 5, boxShadow: libraryFocus === "progress" ? "0 0 0 2px #fff" : "none" } : undefined}>
            <Progress live={live} fraction={fraction} onSeek={onSeek} />
          </div>
          </div>
        </div>
      </div>
    </TouchOnlyScope>
  );
};
