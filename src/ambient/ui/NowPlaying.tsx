import { Focusable, SliderField } from "@decky/ui";
import { createContext, useContext, useState, type CSSProperties, type FC, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { LuGamepad2, LuHeart, LuListMusic, LuListOrdered, LuMinimize2, LuMusic, LuPause, LuPlay, LuRadio, LuRepeat, LuRepeat1, LuShuffle, LuSkipBack, LuSkipForward, LuTv, LuVolume2, LuYoutube } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import { playbackProblem } from "../core/playbackErrors";
import { embedLabel, parseEmbedStream } from "../core/streams";
import type { RepeatMode } from "../core/types";
import { hasYouTubeList, isYouTubeTrack, type PlayerSnapshot } from "../steam/player";

interface Props {
  player: PlayerSnapshot;
  compact?: boolean;
  inGame?: boolean;
  favorite?: boolean;
  onToggle: () => void;
  onNext: () => void;
  onPrevious: () => void;
  onVolume: (volume: number) => void;
  onFavorite?: () => void;
  onBrowse?: () => void;
  /** Present when the track can open in the video window. */
  onVideo?: () => void;
  /** Present when the track can be scrubbed: jump to a fraction of it. */
  onSeek?: (fraction: number) => void;
  /** Controller steps in seconds, forwards or back. */
  onStep?: (seconds: number) => void;
  /** Whether the video is on screen; defaults to the player having it open. */
  videoShown?: boolean;
  /** Present during a game: hands the controller to the floating card. */
  onControl?: () => void;
  /** Shown above the controls, e.g. the slot the shared video window covers. */
  media?: ReactNode;
  /** Compact only: no outer margin or shadow, for cards that float on their own. */
  flush?: boolean;
  /** No gamepad-focusable controls; for players floating outside any navigation tree. */
  touchOnly?: boolean;
  onQueue?: () => void;
  onRepeat?: (repeat: RepeatMode) => void;
  onShuffle?: (on: boolean) => void;
}

const MOTION_CSS = `
@keyframes pdc-np-sheen{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
@keyframes pdc-np-pulse{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes pdc-np-bar{0%,100%{transform:scaleY(.35)}50%{transform:scaleY(1)}}
.pdc-np[data-playing] .pdc-np-sheen{animation:pdc-np-sheen 2.8s ease-in-out infinite}
.pdc-np[data-playing] .pdc-np-live-dot{animation:pdc-np-pulse 1.6s ease-in-out infinite}
.pdc-np[data-playing] .pdc-np-bars>i{animation:pdc-np-bar .9s ease-in-out infinite}
.pdc-np .pdc-np-bars>i:nth-child(2){animation-delay:-.3s}
.pdc-np .pdc-np-bars>i:nth-child(3){animation-delay:-.6s}
.pdc-np-volume div:has([role="slider"]),.pdc-np-volume [role="slider"]{min-width:0!important;width:100%!important;box-sizing:border-box}
.pdc-np-volume .Panel{padding:0!important;margin:0!important;background:transparent!important;border:0!important}
.pdc-np-volume .SliderControl{width:100%!important;height:28px!important}
.pdc-np-volume .SliderTrack{width:calc(100% - 12px)!important;height:4px!important;margin:12px 6px!important;border:0!important;border-radius:4px;background:rgba(255,255,255,.18)!important;box-shadow:none!important}
.pdc-np-volume .SliderTrack::before{height:100%!important;top:0!important;border-radius:inherit;background:rgba(255,255,255,.85)!important;box-shadow:none!important}
.pdc-np-volume .SliderHandleContainer{width:100%!important;transform:none!important}
.pdc-np-volume .SliderHandle{left:calc(var(--normalized-slider-value) * (100% - 12px))!important;top:8px!important;width:12px!important;height:12px!important;border:0!important;border-radius:50%;background:#fff!important;box-shadow:0 0 0 2px rgba(255,255,255,.12)!important}
@media (prefers-reduced-motion:reduce){.pdc-np *{animation:none!important}}
`;

const oneLine: CSSProperties = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

function clock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export const Artwork: FC<{ src: string; label: string; size: number }> = ({ src, label, size }) => (
  <div style={{
    width: size,
    height: size,
    borderRadius: Math.round(size * 0.22),
    flexShrink: 0,
    display: "grid",
    placeItems: "center",
    overflow: "hidden",
    background: src
      ? `center / cover no-repeat url("${src}"), ${theme.color.surfaceRaised}`
      : `radial-gradient(120% 120% at 20% 10%, rgba(${theme.color.accentRgb},0.9), rgba(${theme.color.accentRgb},0.25) 60%, #0c0c10)`,
    boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    color: "#fff",
    fontWeight: 700,
    fontSize: Math.round(size * 0.26),
    textShadow: "0 1px 2px rgba(0,0,0,.5)",
  }}>
    {src ? null : label.replace(/[^\p{L}\p{N}]/gu, "").slice(0, 2).toUpperCase()}
  </div>
);

/**
 * Round control. Themes restyle QAM Focusables (radius, background), so the circle is drawn by an
 * inner element they do not target, and the shared focus ring is asked for a 50% radius.
 */
/**
 * Players floating in Steam's main window over a game must not hold gamepad-focusable nodes:
 * Steam hands them the controller and the Steam and QAM buttons stop working. Those players are
 * driven by touch only.
 */
const TouchOnly = createContext(false);

/** Wraps controls that float over a game: they answer to touch and never take the controller. */
export const TouchOnlyScope: FC<{ children: ReactNode }> = ({ children }) => <TouchOnly.Provider value>{children}</TouchOnly.Provider>;

const ControlRow: FC<{ style: CSSProperties; children: ReactNode }> = ({ style, children }) =>
  useContext(TouchOnly) ? <div style={style}>{children}</div> : <Focusable flow-children="row" style={style}>{children}</Focusable>;

export const RoundButton: FC<{ label: string; onActivate: () => void; size?: number; primary?: boolean; active?: boolean; glass?: boolean; children: ReactNode }> = ({ label, onActivate, size = 36, primary, active, glass, children }) => {
  const touchOnly = useContext(TouchOnly);
  const style = { "--pdc-focus-radius": "50%", borderRadius: "50%", padding: 0, background: "transparent", flexShrink: 0, cursor: "pointer" } as CSSProperties;
  const face = (
    <span style={{
      width: size,
      height: size,
      borderRadius: "50%",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: primary && !glass ? theme.color.onAccent : active ? theme.color.accent : "#fff",
      background: glass
        ? primary ? "rgba(255,255,255,0.22)" : "rgba(255,255,255,0.1)"
        : primary ? theme.color.accent : "rgba(255,255,255,0.07)",
      boxShadow: glass
        ? `inset 0 0 0 1px rgba(255,255,255,${primary ? 0.32 : 0.16}), 0 6px 18px rgba(0,0,0,0.28)`
        : `inset 0 0 0 1px ${theme.color.hairline}`,
    }}>
      {children}
    </span>
  );
  return touchOnly
    ? <div role="button" aria-label={label} onClick={onActivate} style={style}>{face}</div>
    : <Focusable aria-label={label} onActivate={onActivate} onClick={onActivate} style={style}>{face}</Focusable>;
};

const NEXT_REPEAT: Record<RepeatMode, RepeatMode> = { all: "one", one: "off", off: "all" };

export const RepeatButton: FC<{ repeat: RepeatMode; onChange: (repeat: RepeatMode) => void; size?: number; glass?: boolean }> = ({ repeat, onChange, size = 36, glass }) => {
  const { t } = useI18n();
  return (
    <RoundButton glass={glass} label={t(`ambient.repeat.${repeat}`)} active={repeat !== "off"} size={size} onActivate={() => onChange(NEXT_REPEAT[repeat])}>
      {repeat === "one" ? <LuRepeat1 size={15} /> : <LuRepeat size={15} style={{ opacity: repeat === "off" ? 0.55 : 1 }} />}
    </RoundButton>
  );
};

export const ShuffleButton: FC<{ shuffle: boolean; onChange: (on: boolean) => void; size?: number; glass?: boolean }> = ({ shuffle, onChange, size = 36, glass }) => {
  const { t } = useI18n();
  return (
    <RoundButton glass={glass} label={t(shuffle ? "ambient.shuffle.on" : "ambient.shuffle.off")} active={shuffle} size={size} onActivate={() => onChange(!shuffle)}>
      <LuShuffle size={15} style={{ opacity: shuffle ? 1 : 0.55 }} />
    </RoundButton>
  );
};

/** The artwork, blurred, becomes the card itself: every station or song tints its own player. */
const Backdrop: FC<{ art: string }> = ({ art }) => (
  <>
    <div aria-hidden style={{
      position: "absolute",
      inset: -24,
      background: art
        ? `center / cover no-repeat url("${art}")`
        : `radial-gradient(90% 80% at 15% 10%, rgba(${theme.color.accentRgb},0.75), transparent 70%), radial-gradient(80% 90% at 90% 100%, rgba(${theme.color.accentRgb},0.35), transparent 70%), #0b0d12`,
      filter: art ? "blur(26px) saturate(1.5) brightness(0.62)" : "none",
      transform: "scale(1.08)",
    }} />
    <div aria-hidden style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.25) 45%, rgba(0,0,0,0.6) 100%)" }} />
  </>
);

const Bars: FC = () => (
  <span className="pdc-np-bars" aria-hidden style={{ display: "inline-flex", alignItems: "flex-end", gap: 2, height: 12 }}>
    {[0, 1, 2].map((i) => <i key={i} style={{ display: "block", width: 3, height: 12, borderRadius: 1.5, background: "#fff", transformOrigin: "bottom" }} />)}
  </span>
);

const SEEK_STEP_SECONDS = 10;
const DPAD_LEFT = 11;
const DPAD_RIGHT = 12;

/** Progress that scrubs: drag it, or press left and right on it with a controller. */
export const Progress: FC<{ live: boolean; fraction: number; onSeek?: (fraction: number) => void; onStep?: (seconds: number) => void }> = ({ live, fraction, onSeek, onStep }) => {
  const touchOnly = useContext(TouchOnly);
  const [dragging, setDragging] = useState<number | null>(null);
  const shown = dragging ?? fraction;
  const fill = live ? 1 : Math.max(0, Math.min(1, shown));
  const accent = `rgb(${theme.color.accentRgb})`;
  const seekable = !live && !!onSeek;
  const at = (event: ReactPointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
  };
  const bar = (
    <div
      onPointerDown={seekable ? (event) => {
        event.stopPropagation();
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(at(event));
      } : undefined}
      onPointerMove={seekable ? (event) => dragging !== null && setDragging(at(event)) : undefined}
      onPointerUp={seekable ? (event) => {
        event.stopPropagation();
        onSeek?.(at(event));
        setDragging(null);
      } : undefined}
      onPointerCancel={() => setDragging(null)}
      style={{ position: "relative", height: 16, display: "flex", alignItems: "center", cursor: seekable ? "pointer" : "default", touchAction: "none" }}
    >
      <div style={{ position: "absolute", left: 0, right: 0, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.18)" }} />
      <div style={{
        position: "absolute",
        left: 0,
        width: `${fill * 100}%`,
        height: 4,
        borderRadius: 2,
        overflow: "hidden",
        background: `linear-gradient(90deg, rgba(255,255,255,0.55), #fff 55%, ${accent})`,
        boxShadow: `0 0 10px rgba(${theme.color.accentRgb},0.65)`,
      }}>
        {live && <div className="pdc-np-sheen" style={{ position: "absolute", top: 0, bottom: 0, width: "40%", background: `linear-gradient(90deg, transparent, rgba(${theme.color.accentRgb},0.95), transparent)` }} />}
      </div>
      {!live && (
        <div style={{
          position: "absolute",
          left: `calc(${fill * 100}% - 7px)`,
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: accent,
          boxShadow: `0 0 0 2.5px #fff, 0 0 14px 4px rgba(${theme.color.accentRgb},0.7)`,
        }} />
      )}
    </div>
  );
  if (!seekable || !onStep || touchOnly) return bar;
  return (
    <Focusable
      onButtonDown={(event: { detail?: { button?: number } }) => {
        const button = event.detail?.button;
        if (button === DPAD_LEFT) onStep(-SEEK_STEP_SECONDS);
        else if (button === DPAD_RIGHT) onStep(SEEK_STEP_SECONDS);
      }}
      style={{ borderRadius: 8 } as CSSProperties}
    >
      {bar}
    </Focusable>
  );
};

const NowPlayingBody: FC<Props> = ({ player, compact, inGame, favorite, onToggle, onNext, onPrevious, onVolume, onFavorite, onBrowse, onVideo, videoShown, onControl, onSeek, onStep, media, flush, onQueue, onRepeat, onShuffle }) => {
  const showingVideo = videoShown ?? player.video;
  const { t } = useI18n();
  const track = player.track;
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";
  const live = !!track?.live;
  const youtube = !!track && isYouTubeTrack(track);
  const skippable = !!track && (player.queue.length > 1 || (!live && (!youtube || hasYouTubeList(track))));
  const title = track?.title ?? t("ambient.player.idle");
  const art = track?.art ?? "";
  const statusText = {
    idle: t("ambient.player.idle"),
    loading: t("ambient.player.loading"),
    retrying: t("ambient.player.retrying"),
    error: track ? t(`ambient.err.${playbackProblem(track.url, player.error)}`) : t("ambient.player.error"),
    playing: inGame ? t("ambient.player.inGame") : track?.subtitle || "",
    paused: track?.subtitle || "",
  }[player.status];
  const embed = track ? parseEmbedStream(track.url) : null;
  const source = youtube ? "YouTube" : embed ? embedLabel(embed) : live ? t("ambient.music.radio") : t("ambient.music.mine");
  const fraction = player.duration ? player.position / player.duration : 0;
  const shell: CSSProperties = {
    position: "relative",
    overflow: "hidden",
    borderRadius: compact ? 18 : 24,
    marginBottom: flush ? 0 : theme.space.card,
    color: "#fff",
    isolation: "isolate",
    boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.08), 0 10px 28px rgba(0,0,0,0.35)`,
  };
  const playIcon = busy ? <LuPause size={compact ? 16 : 20} /> : <LuPlay size={compact ? 16 : 20} style={{ marginLeft: 3 }} />;
  const toggleLabel = busy ? t("ambient.player.pause") : t("ambient.player.play");

  if (compact) {
    return (
      <div className="pdc-np" data-playing={player.status === "playing" ? "" : undefined} style={shell}>
        <style>{MOTION_CSS}</style>
        <Backdrop art={art} />
        {media}
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 10, padding: "12px 12px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Artwork src={art} label={title} size={44} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
              <span style={{ ...oneLine, fontSize: 13, fontWeight: 700 }}>{title}</span>
              <span style={{ ...oneLine, fontSize: theme.font.caption, color: player.status === "error" ? theme.color.warn : "rgba(255,255,255,0.72)" }}>{statusText}</span>
            </div>
            <ControlRow style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <RoundButton glass primary label={toggleLabel} onActivate={onToggle} size={40}>{playIcon}</RoundButton>
              {skippable && <RoundButton glass label={t("ambient.player.next")} onActivate={onNext} size={36}><LuSkipForward size={15} /></RoundButton>}
              {!skippable && onFavorite && (
                <RoundButton glass label={favorite ? t("ambient.stations.unfavorite") : t("ambient.stations.favorite")} onActivate={onFavorite} active={favorite} size={36}>
                  <LuHeart size={15} fill={favorite ? "currentColor" : "none"} />
                </RoundButton>
              )}
              {onVideo && (
                <RoundButton glass label={showingVideo ? t("ambient.player.hideVideo") : t("ambient.player.showVideo")} onActivate={onVideo} size={36}>
                  {showingVideo ? <LuMinimize2 size={15} /> : <LuTv size={15} />}
                </RoundButton>
              )}
              {onControl && (
                <RoundButton glass label={t("ambient.player.control")} onActivate={onControl} size={32}>
                  <LuGamepad2 size={14} />
                </RoundButton>
              )}
            </ControlRow>
          </div>
          {track && <Progress live={live} fraction={fraction} onSeek={onSeek} onStep={onStep} />}
        </div>
      </div>
    );
  }

  return (
    <div className="pdc-np" data-playing={player.status === "playing" ? "" : undefined} style={shell}>
      <style>{MOTION_CSS}</style>
      <Backdrop art={art} />
      {media}
      <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px 6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.86)", flex: 1, minWidth: 0 }}>
            {youtube ? <LuYoutube size={13} /> : live ? <LuRadio size={13} /> : <LuMusic size={13} />}
            <span style={oneLine}>{source}</span>
          </span>
          {player.status === "playing" && (live
            ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", padding: "3px 8px", borderRadius: 99, background: "rgba(0,0,0,0.35)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.14)" }}>
                <span className="pdc-np-live-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "#ff4d4d", boxShadow: "0 0 6px #ff4d4d" }} />
                {t("ambient.player.live")}
              </span>
            )
            : <Bars />)}
          {onControl && (
            <RoundButton glass label={t("ambient.player.control")} onActivate={onControl} size={30}>
              <LuGamepad2 size={13} />
            </RoundButton>
          )}
          {onVideo && (
            <RoundButton glass label={showingVideo ? t("ambient.player.hideVideo") : t("ambient.player.showVideo")} onActivate={onVideo} size={30}>
              {showingVideo ? <LuMinimize2 size={13} /> : <LuTv size={13} />}
            </RoundButton>
          )}
          {onQueue && (
            <RoundButton glass label={t("ambient.queue.title")} onActivate={onQueue} size={30}>
              <LuListOrdered size={13} />
            </RoundButton>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, textAlign: "center" }}>
          <span style={{ ...oneLine, maxWidth: "100%", fontSize: 16, fontWeight: 800, letterSpacing: -0.2, lineHeight: 1.2, textShadow: "0 2px 10px rgba(0,0,0,0.45)" }}>{title}</span>
          <span style={{ ...oneLine, maxWidth: "100%", fontSize: theme.font.caption, color: player.status === "error" ? theme.color.warn : "rgba(255,255,255,0.72)" }}>{statusText}</span>
        </div>

        {track && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <Progress live={live} fraction={fraction} onSeek={onSeek} onStep={onStep} />
            {!live && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontVariantNumeric: "tabular-nums", color: "rgba(255,255,255,0.7)" }}>
                <span>{clock(player.position)}</span>
                <span>{player.duration ? clock(player.duration) : "–:––"}</span>
              </div>
            )}
          </div>
        )}

        <ControlRow style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
          {onShuffle && skippable && <ShuffleButton glass size={30} shuffle={player.shuffle} onChange={onShuffle} />}
          {!skippable
            ? onFavorite && (
              <RoundButton glass label={favorite ? t("ambient.stations.unfavorite") : t("ambient.stations.favorite")} onActivate={onFavorite} active={favorite} size={36}>
                <LuHeart size={15} fill={favorite ? "currentColor" : "none"} />
              </RoundButton>
            )
            : <RoundButton glass label={t("ambient.player.previous")} onActivate={onPrevious} size={36}><LuSkipBack size={15} fill="currentColor" /></RoundButton>}
          <RoundButton glass primary label={toggleLabel} onActivate={onToggle} size={50}>{playIcon}</RoundButton>
          {!skippable
            ? onBrowse && <RoundButton glass label={t("ambient.stations.browse")} onActivate={onBrowse} size={36}><LuListMusic size={15} /></RoundButton>
            : <RoundButton glass label={t("ambient.player.next")} onActivate={onNext} size={36}><LuSkipForward size={15} fill="currentColor" /></RoundButton>}
          {onRepeat && skippable && <RepeatButton glass size={30} repeat={player.repeat} onChange={onRepeat} />}
        </ControlRow>

        <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, padding: "2px 2px 6px" }}>
          <LuVolume2 size={14} style={{ color: "rgba(255,255,255,0.75)", flexShrink: 0 }} />
          <div className="pdc-np-volume" style={{ flex: 1, minWidth: 0 }}>
            <SliderField value={Math.round(player.volume * 100)} min={0} max={100} step={5} showValue={false} childrenContainerWidth="max" bottomSeparator="none" onChange={(v) => onVolume(v / 100)} />
          </div>
        </div>
      </div>
    </div>
  );
};

export const NowPlaying: FC<Props> = (props) => (
  <TouchOnly.Provider value={!!props.touchOnly}>
    <NowPlayingBody {...props} />
  </TouchOnly.Provider>
);
