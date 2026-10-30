import { findSP } from "@decky/ui";
import { useEffect, useState, type FC } from "react";
import { createPortal } from "react-dom";

import { qamPanelWidth, subscribeQamSurface, type QamSurface } from "../../platform/qamSurface";
import { useI18n } from "../../i18n";
import { NowPlaying } from "./NowPlaying";
import { useAmbient } from "./useAmbient";

const HOST_ID = "pdc-ambient-qam-player";
const GAP_PX = 14;
const WIDTH_PX = 300;
const SETTLE_MS = 320;

function mainDocument(): Document | null {
  try {
    return findSP()?.document ?? null;
  } catch {
    return null;
  }
}

/**
 * Mini player beside the QAM. The QAM window starts at the panel's edge, so the player lives in
 * Steam's main window, which Steam also shows over a running game while the QAM is open; it sits
 * just left of the panel, measured from the QAM's layout, and only while the QAM is open.
 */
export const QamSidePlayer: FC = () => {
  const { runtime, snapshot } = useAmbient();
  const { t } = useI18n();
  const [surface, setSurface] = useState<QamSurface | null>(null);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const [right, setRight] = useState<number | null>(null);

  useEffect(() => subscribeQamSurface(setSurface), []);

  useEffect(() => {
    const doc = mainDocument();
    if (!doc?.body) return;
    doc.getElementById(HOST_ID)?.remove();
    const node = doc.createElement("div");
    node.id = HOST_ID;
    doc.body.appendChild(node);
    setHost(node);
    return () => {
      node.remove();
      setHost(null);
    };
  }, []);

  useEffect(() => {
    if (!surface?.visible) {
      setRight(null);
      return;
    }
    const mainView = host?.ownerDocument.defaultView;
    if (!mainView) return;
    const measure = () => {
      const panel = qamPanelWidth(surface.document);
      setRight(panel !== null && panel + GAP_PX + WIDTH_PX < mainView.innerWidth ? panel + GAP_PX : null);
    };
    measure();
    const settle = mainView.setTimeout(measure, SETTLE_MS);
    return () => mainView.clearTimeout(settle);
  }, [surface?.visible, surface?.document, host]);

  const settings = snapshot?.state?.settings;
  const player = snapshot?.player;
  const show = !!runtime && !!host && right !== null && settings?.music.qamPlayer !== false && !!player?.track && !(player.video && !snapshot?.videoCollapsed) && !snapshot?.pageOpen;
  if (!show || !runtime || !player || !host || right === null) return null;
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";

  return createPortal(
    <div style={{ position: "fixed", zIndex: 2147483000, bottom: 18, right, width: WIDTH_PX }}>
      <NowPlaying
        compact
        touchOnly
        inGame={!!snapshot?.inGame}
        player={player}
        onToggle={() => (busy ? runtime.pauseMusic() : runtime.resumeMusic())}
        onNext={() => runtime.nextTrack()}
        onPrevious={() => runtime.previousTrack()}
        onVolume={(v) => runtime.setVolume(v)}
        onSeek={(f) => runtime.seekFraction(f)}
        favorite={runtime.isFavoriteTrack()}
        onFavorite={runtime.canFavoriteTrack() ? () => runtime.toggleFavoriteTrack() : undefined}
        videoShown={player.video && !snapshot?.videoCollapsed}
        onVideo={runtime.canShowVideo() ? () => runtime.toggleVideo() : undefined}
      />
      <div
        role="button"
        onClick={() => runtime.startOverlayControl()}
        style={{ marginTop: -4, textAlign: "right", fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.8)", textShadow: "0 1px 6px rgba(0,0,0,0.6)", cursor: "pointer" }}
      >
        {t("ambient.overlay.leftHint")}
      </div>
    </div>,
    host,
  );
};
