import { Focusable, GamepadButton, type GamepadEvent } from "@decky/ui";
import { useState, type FC, type ReactNode } from "react";
import { LuArrowUpDown, LuListX, LuSmartphone } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { QueueItem } from "../steam/player";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { Artwork, RepeatButton, ShuffleButton } from "./NowPlaying";
import { Button, Row, menuHandlers, type ItemMenu } from "./primitives";
import { Empty, ROW_HEIGHT, useMeasuredHeight } from "./stationsParts";
import { SharePanel } from "./SharePanel";
import { VirtualList } from "./VirtualList";

export const QueueTab: FC<{ runtime: AmbientRuntime; snapshot: AmbientSnapshot; header: ReactNode }> = ({ runtime, snapshot, header }) => {
  const { t } = useI18n();
  const [listRef, listHeight] = useMeasuredHeight();
  const [moving, setMoving] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const player = snapshot.player;
  const queue = player.queue;

  const menu = (entry: QueueItem, index: number): ItemMenu => ({
    title: entry.track.title,
    hint: t("ambient.menu.options"),
    actions: [
      { label: t("ambient.queue.play"), onSelect: () => runtime.playQueueEntry(entry.key) },
      { label: t("ambient.queue.move"), onSelect: () => setMoving(entry.key) },
      ...index > 0 ? [{ label: t("ambient.queue.moveUp"), onSelect: () => runtime.moveQueueEntry(entry.key, index - 1) }] : [],
      ...index < queue.length - 1 ? [{ label: t("ambient.queue.moveDown"), onSelect: () => runtime.moveQueueEntry(entry.key, index + 1) }] : [],
      { label: t("ambient.queue.remove"), destructive: true, onSelect: () => runtime.removeQueueEntry(entry.key) },
    ],
  });

  const moveWithPad = (entry: QueueItem, index: number) => (event: GamepadEvent) => {
    const step = event.detail.button === GamepadButton.DIR_UP ? -1 : event.detail.button === GamepadButton.DIR_DOWN ? 1 : 0;
    if (!step) return;
    event.preventDefault();
    event.stopPropagation();
    runtime.moveQueueEntry(entry.key, index + step);
  };

  return (
    <>
      {header}
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
        <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
          <ShuffleButton shuffle={player.shuffle} onChange={(on) => runtime.setShuffle(on)} />
          <RepeatButton repeat={player.repeat} onChange={(repeat) => runtime.setRepeat(repeat)} />
        </Focusable>
        <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {moving ? t("ambient.queue.moving") : queue.length ? t("ambient.queue.count", { n: String(queue.length) }) : ""}
        </span>
        {!sharing && <Button label={<><LuSmartphone size={14} /> {t("ambient.share.open")}</>} onActivate={() => setSharing(true)} />}
        {queue.length > 1 && <Button label={<><LuListX size={14} /> {t("ambient.queue.clear")}</>} onActivate={() => runtime.clearQueue()} />}
      </div>
      {sharing ? <SharePanel runtime={runtime} onClose={() => setSharing(false)} /> : <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
        {queue.length === 0
          ? <Empty text={t("ambient.queue.empty")} />
          : listHeight > 0 && <VirtualList controllerNavigation items={queue} rowHeight={ROW_HEIGHT} height={listHeight} keyOf={(entry) => entry.key} renderRow={(entry, index) => (
            <Focusable
              {...menuHandlers(moving ? undefined : menu(entry, index))}
              onGamepadDirection={moving === entry.key ? moveWithPad(entry, index) : undefined}
              onCancelButton={moving === entry.key ? (event: GamepadEvent) => { event.preventDefault(); event.stopPropagation(); setMoving(null); } : undefined}
            >
              <Row
                title={entry.track.title}
                subtitle={entry.track.subtitle || undefined}
                swatch={<Artwork src={entry.track.art} label={entry.track.title} size={32} />}
                selected={moving ? moving === entry.key : index === player.queueIndex}
                trailing={moving === entry.key ? <LuArrowUpDown size={16} style={{ color: theme.color.accent }} /> : undefined}
                onActivate={() => (moving ? setMoving(null) : runtime.playQueueEntry(entry.key))}
              />
            </Focusable>
          )} />}
      </div>}
    </>
  );
};
