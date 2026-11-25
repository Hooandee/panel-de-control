import { useLayoutEffect, useRef, type FC } from "react";
import { Focusable, GamepadButton } from "@decky/ui";
import { LuPause, LuPlay } from "react-icons/lu";
import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { RoundButton } from "./NowPlaying";
import { registerLibraryDock, setLibraryDockFocus, type LibraryControl } from "./libraryDock";

export const LibraryPlayback: FC<{ runtime: AmbientRuntime; player: AmbientSnapshot["player"]; inline?: boolean }> = ({ runtime, player, inline = false }) => {
  const { t } = useI18n();
  if (!player.track) return null;
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";
  if (!inline) return <LibraryPlayerDock runtime={runtime} player={player} />;
  return <div role="group" aria-label={t("ambient.player.title")} style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, maxWidth: "55%", minWidth: 0 }}>
    <span style={{ overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis", fontSize: theme.font.caption }}>{player.track.title}</span>
    <RoundButton label={t(busy ? "ambient.player.pause" : "ambient.player.play")} size={32} onActivate={() => busy ? runtime.pauseMusic() : runtime.resumeMusic()}>
      {busy ? <LuPause size={15} /> : <LuPlay size={15} />}
    </RoundButton>
  </div>;
};

const LibraryPlayerDock: FC<{ runtime: AmbientRuntime; player: AmbientSnapshot["player"] }> = ({ runtime, player }) => {
  const { t } = useI18n();
  const anchor = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = anchor.current;
    if (!element) return undefined;
    const release = registerLibraryDock({ runtime, element });
    return release;
  }, [runtime]);
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";
  const duration = player.duration ?? 0;
  const seekable = player.video && !player.track?.live && Number.isFinite(duration) && duration > 0;
  const focus = (control: LibraryControl) => { if (anchor.current) setLibraryDockFocus(anchor.current, control); };
  const blur = (control: LibraryControl) => { if (anchor.current) setLibraryDockFocus(anchor.current, null, control); };
  const toggle = () => busy ? runtime.pauseMusic() : runtime.resumeMusic();
  return <Focusable
    flow-children="column"
    onActivate={player.video ? undefined : toggle}
    onOKActionDescription={player.video ? undefined : t(busy ? "ambient.player.pause" : "ambient.player.play")}
    onOptionsActionDescription={player.video ? t("ambient.player.fullscreen") : undefined}
    onOptionsButton={player.video ? (event) => { event.preventDefault(); event.stopPropagation(); if (runtime.getSnapshot().videoCollapsed) runtime.toggleVideo(); runtime.setVideoFullscreen(!runtime.getSnapshot().videoFullscreen); } : undefined}
    style={{ flexShrink: 0, width: "100%", borderRadius: 18 }}
  ><div ref={anchor} data-library-player-dock style={{ position: "relative", width: "100%", minHeight: 100, aspectRatio: player.video ? "16 / 9" : undefined }}>
    {player.video && <>
      {/* Navigation stays in the modal; the single body-level video card draws these controls. */}
      <Focusable
        data-library-control="toggle" noFocusRing
        aria-label={t(busy ? "ambient.player.pause" : "ambient.player.play")}
        onOKActionDescription={t(busy ? "ambient.player.pause" : "ambient.player.play")}
        onActivate={(event) => { event.stopPropagation(); toggle(); }}
        onGamepadFocus={() => focus("toggle")} onGamepadBlur={() => blur("toggle")}
        style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", width: 42, height: 42 }}
      ><span /></Focusable>
      {seekable && <Focusable
        data-library-control="progress" noFocusRing {...{ focusable: true }} role="slider" aria-label={t("ambient.player.position")}
        aria-valuemin={0} aria-valuemax={duration} aria-valuenow={player.position}
        onGamepadFocus={() => focus("progress")} onGamepadBlur={() => blur("progress")}
        onGamepadDirection={(event) => {
          const direction = event.detail.button;
          if (direction !== GamepadButton.DIR_LEFT && direction !== GamepadButton.DIR_RIGHT) return false;
          event.preventDefault(); event.stopPropagation();
          runtime.seekBy(direction === GamepadButton.DIR_LEFT ? -10 : 10);
          return true;
        }}
        style={{ position: "absolute", left: 12, right: 12, bottom: 8, height: 16 }}
      ><span /></Focusable>}
    </>}
  </div></Focusable>;
};
