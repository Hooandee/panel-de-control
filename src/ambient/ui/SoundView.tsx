import { useEffect, type FC } from "react";
import type { ReactNode } from "react";
import { LuLibrary, LuFilm, LuFolderPlus, LuMusic, LuRadio, LuTv, LuTwitch, LuYoutube } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { OverlayCorner, OverlayMode } from "../core/types";
import { parseEmbedStream } from "../core/streams";
import { isHls, parseYouTube } from "../core/youtube";
import { favoriteToStation, type AmbientRuntime, type AmbientSnapshot } from "../steam/runtime";
import { trackSource } from "../steam/player";
import { NowPlaying } from "./NowPlaying";
import { Button, Caption, ChoiceRow, ToggleRow, CornerPicker, MoreSettings, SliderRow, Tile, TileStrip, cardStyle } from "./primitives";
import { openMediaLibrary } from "./StationsModal";

const MUSIC_SWATCH = "linear-gradient(135deg,#3a2a60,#8a4a8a)";
const STATION_SWATCH = "linear-gradient(135deg,#1d2a3a,#2f4a66)";

function kindBadge(url: string): ReactNode {
  if (parseYouTube(url)) return <LuYoutube size={12} />;
  const embed = parseEmbedStream(url);
  if (embed?.provider === "twitch") return <LuTwitch size={12} />;
  if (embed) return <LuFilm size={12} />;
  return isHls(url) ? <LuTv size={12} /> : <LuRadio size={12} />;
}

export const SoundView: FC<{ snapshot: AmbientSnapshot; runtime: AmbientRuntime }> = ({ snapshot, runtime }) => {
  const { t } = useI18n();
  useEffect(() => runtime.markPageOpen(), [runtime]);
  const settings = snapshot.state!.settings;
  const music = settings.music;
  const player = snapshot.player;
  const track = player.track;
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";
  const songs = snapshot.scan?.music.length ?? 0;
  const setMusic = (patch: Partial<typeof music>) => void runtime.updateSettings((s) => ({ ...s, music: { ...s.music, ...patch } }));
  const playingMine = !!track && trackSource(track) === "music";
  const level = (value: number) => (value === 0 ? t("ambient.short.pause") : `${value} %`);
  const corners = Object.fromEntries((["top-left", "top-right", "bottom-left", "bottom-right"] as OverlayCorner[]).map((c) => [c, t(`ambient.overlay.${c}`)])) as Record<OverlayCorner, string>;

  const playMine = () => {
    if (!songs) return void addMusicFolder();
    void runtime.updateSettings((s) => ({ ...s, music: { ...s.music, source: "music", enabled: true } })).then(() => runtime.playMyMusic());
  };

  const addMusicFolder = () => openMediaLibrary("music");

  return (
    <div style={cardStyle}>
      {snapshot.floatingMissing && (
        <span role="status" style={{ display: "block", marginBottom: theme.space.sm, fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.35 }}>
          {t("ambient.floating.missing")}
        </span>
      )}
      {track || music.enabled ? (
        <NowPlaying
          flush
          player={player}
          favorite={runtime.isFavoriteTrack()}
          onFavorite={runtime.canFavoriteTrack() ? () => runtime.toggleFavoriteTrack() : undefined}
          onBrowse={() => openMediaLibrary("music")}
          onToggle={() => (busy ? runtime.pauseMusic() : runtime.resumeMusic())}
          onNext={() => runtime.nextTrack()}
          onPrevious={() => runtime.previousTrack()}
          onVolume={(v) => runtime.setVolume(v)}
          onSeek={(f) => runtime.seekFraction(f)}
          onStep={(sec) => runtime.seekBy(sec)}
          videoShown={player.video && !snapshot.videoCollapsed}
          onVideo={runtime.canShowVideo() ? () => runtime.toggleVideo() : undefined}
          onControl={snapshot.inGame && track ? () => runtime.startOverlayControl() : undefined}
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: `${theme.space.md}px 0`, textAlign: "center" }}>
          <LuMusic size={22} style={{ color: theme.color.accent }} />
          <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>{t("ambient.sound.empty")}</span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("ambient.sound.empty.desc")}</span>
        </div>
      )}

      <Button label={<><LuLibrary size={14} /> {t("ambient.lib.open")}</>} onActivate={() => openMediaLibrary("music")} />

      <Caption>{t("ambient.radio.favorites")}</Caption>
      <TileStrip>
        <Tile
          label={songs ? t("ambient.music.mine") : t("ambient.music.addFolder")}
          background={MUSIC_SWATCH}
          icon={songs ? <LuMusic size={22} color="#fff" /> : <LuFolderPlus size={20} color="#fff" />}
          selected={playingMine}
          activateHint={t("ambient.menu.play")}
          menu={{ title: t("ambient.music.mine"), hint: t("ambient.menu.options"), actions: [{ label: t("ambient.lib.manage"), onSelect: () => openMediaLibrary("music") }] }}
          onActivate={playMine}
        />
        {settings.radio.favorites.map((f) => {
          const station = favoriteToStation(f);
          return (
            <Tile
              key={f.id}
              label={f.name}
              image={f.art || null}
              background={STATION_SWATCH}
              icon={f.art ? undefined : <LuRadio size={20} color="#fff" />}
              selected={track?.url === f.url}
              badge={kindBadge(f.url)}
              activateHint={t("ambient.menu.play")}
              menu={{ title: f.name, hint: t("ambient.menu.options"), actions: [
                { label: t("ambient.menu.play"), onSelect: () => runtime.playStation(station) },
                { label: t("ambient.lib.remove"), destructive: true, onSelect: () => void runtime.removeItem("radio", f.id) },
              ] }}
              onActivate={() => runtime.playStation(station)}
            />
          );
        })}
      </TileStrip>

      <Caption>{t("ambient.mix.title")}</Caption>
      <SliderRow label={t("ambient.mix.media")} value={music.inGameMediaLevel} min={0} max={100} step={5} format={level} onChange={(inGameMediaLevel) => setMusic({ inGameMediaLevel })} />
      <SliderRow label={t("ambient.mix.game")} value={music.inGameGameLevel} min={0} max={100} step={5} format={(v) => `${v} %`} onChange={(inGameGameLevel) => setMusic({ inGameGameLevel })} />
      <ToggleRow label={t("ambient.game.themes")} description={t("ambient.game.themes.desc")} checked={settings.background.gameThemes} onChange={(gameThemes) => void runtime.updateSettings((s) => ({ ...s, background: { ...s.background, gameThemes } }))} />
      <ChoiceRow
        label={t("ambient.sound.overGame")}
        value={music.overlay}
        options={(["off", "peek", "always"] as OverlayMode[]).map((m) => ({ value: m, label: t(m === "peek" ? "ambient.short.peek" : `ambient.overlay.${m}`) }))}
        onChange={(overlay) => setMusic({ overlay })}
      />

      <MoreSettings id="ambient-sound-more" label={t("ambient.more")}>
        <CornerPicker label={t("ambient.overlay.corner")} value={music.overlayCorner} labels={corners} onChange={(overlayCorner) => setMusic({ overlayCorner })} />
        <SliderRow label={t("ambient.overlay.videoSize")} value={music.videoScale} min={20} max={70} step={5} format={(v) => `${v} %`} onChange={(videoScale) => setMusic({ videoScale })} />
        <ToggleRow label={t("ambient.music.qamPlayer")} description={t("ambient.music.qamPlayer.desc")} checked={music.qamPlayer} onChange={(qamPlayer) => setMusic({ qamPlayer })} />
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>{t("ambient.overlay.mode.desc")}</span>
      </MoreSettings>
    </div>
  );
};
