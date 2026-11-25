import { useState, type FC } from "react";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import { readFlag, writeFlag } from "../../platform/preferences";
import { BackgroundView } from "./BackgroundView";
import { ConflictCard } from "./ConflictCard";
import { NowPlaying } from "./NowPlaying";
import { Button, Segmented, cardStyle } from "./primitives";
import { SoundView } from "./SoundView";
import { useAmbient } from "./useAmbient";

type Tab = "background" | "sound";
const TAB_KEY = "pdc:ambient:sound-tab";

export const AmbienteSection: FC = () => {
  const { t } = useI18n();
  const { runtime, snapshot } = useAmbient();
  const [tab, setTab] = useState<Tab>(() => (readFlag(TAB_KEY, false) ? "sound" : "background"));
  const chooseTab = (next: Tab) => {
    setTab(next);
    writeFlag(TAB_KEY, next === "sound");
  };
  if (!runtime || !snapshot || !snapshot.ready) {
    return <div style={{ ...cardStyle, alignItems: "center", color: theme.color.textMuted, fontSize: theme.font.caption }}>…</div>;
  }
  if (!snapshot.state) {
    return (
      <div style={cardStyle}>
        <div style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("ambient.error.backend")}</div>
        <Button label={t("ambient.retry")} onActivate={() => void runtime.reload()} />
      </div>
    );
  }
  const { conflict } = snapshot.decision;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {conflict && (
        <ConflictCard
          conflict={conflict}
          currentUrl={snapshot.currentUrl}
          onChoose={(owner) => void runtime.choose(conflict.id, owner)}
        />
      )}
      <Segmented
        value={tab}
        options={[{ value: "background", label: t("ambient.tab.background") }, { value: "sound", label: t("ambient.tab.sound") }]}
        onChange={(value) => chooseTab(value as Tab)}
      />
      {tab === "background"
        ? <BackgroundView snapshot={snapshot} runtime={runtime} />
        : <SoundView snapshot={snapshot} runtime={runtime} />}
    </div>
  );
};

export const AmbientPlayerBlock: FC = () => {
  const { runtime, snapshot } = useAmbient();
  if (!runtime || !snapshot?.player.track) return null;
  const playing = snapshot.player.status === "playing" || snapshot.player.status === "loading" || snapshot.player.status === "retrying";
  return (
    <NowPlaying
      compact
      inGame={snapshot.inGame}
      player={snapshot.player}
      onToggle={() => (playing ? runtime.pauseMusic() : runtime.resumeMusic())}
      onNext={() => runtime.nextTrack()}
      onPrevious={() => runtime.previousTrack()}
      onVolume={(v) => runtime.setVolume(v)}
      onSeek={(f) => runtime.seekFraction(f)}
      onStep={(sec) => runtime.seekBy(sec)}
      onControl={snapshot.inGame ? () => runtime.startOverlayControl() : undefined}
    />
  );
};
