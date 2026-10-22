import { DialogButton, Focusable, GamepadButton, GamepadEvent, TextField } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { LuCalendar, LuClock3, LuGauge, LuImage, LuMove, LuSend, LuSparkles, LuTrash2, LuType } from "react-icons/lu";

import { DrawingSummary, listAccessoryDrawings, previewAccessoryScene } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { decodeFrames, DecodedFrames, PANEL_H, PANEL_W } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";

export interface Block {
  type: "clock" | "date" | "text" | "metric" | "icon" | "drawing";
  x: number;
  y: number;
  size: "s" | "m" | "l";
  color: string;
  text?: string;
  metric?: string;
  icon?: string;
  drawing?: string;
}

const COLORS = ["aurora", "sunset", "mint", "mono"];
const SIZES: Block["size"][] = ["s", "m", "l"];
const METRICS = ["cpu_pct", "gpu_pct", "ram_pct", "fps", "gpu_w", "gpu_temp", "cpu_temp"];
const ICONS = ["heart", "star", "pad", "bolt"];
const MAX_BLOCKS = 20;

export const STARTER_LAYOUT: Block[] = [
  { type: "date", x: 4, y: 3, size: "m", color: "aurora" },
  { type: "clock", x: 3, y: 13, size: "l", color: "aurora" },
  { type: "icon", x: 4, y: 38, size: "m", icon: "heart", color: "sunset" },
  { type: "metric", x: 22, y: 41, size: "m", metric: "fps", color: "mint" },
];

const next = <T,>(list: T[], value: T | undefined): T => list[(list.indexOf(value as T) + 1) % list.length];

export const ComposerBody: FC<{ pitch?: number; onDirty?: () => void; initial: Block[]; onShow: (blocks: Block[]) => void; closeModal?: () => void }> = ({ initial, onShow, closeModal, onDirty, pitch = 6 }) => {
  const { t } = useI18n();
  const [blocks, setBlocks] = useState<Block[]>(initial.length ? initial : STARTER_LAYOUT);
  const [selected, setSelected] = useState(0);
  const [preview, setPreview] = useState<DecodedFrames | null>(null);
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const [grabbing, setGrabbing] = useState(false);

  useEffect(() => {
    void listAccessoryDrawings().then((result) => setDrawings(result?.drawings ?? [])).catch(() => setDrawings([]));
  }, []);
  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      void previewAccessoryScene("composed", { layout: { blocks } })
        .then((frames) => { if (live && frames && frames.ok !== false) setPreview(decodeFrames(frames)); })
        .catch(() => undefined);
    }, 220);
    return () => { live = false; window.clearTimeout(timer); };
  }, [JSON.stringify(blocks)]);

  const current = blocks[selected];
  const update = (patch: Partial<Block>) => {
    if (!current) return;
    onDirty?.();
    setBlocks(blocks.map((block, i) => (i === selected ? { ...block, ...patch } : block)));
  };
  const add = (block: Block) => {
    if (blocks.length >= MAX_BLOCKS) return;
    onDirty?.();
    setBlocks([...blocks, block]);
    setSelected(blocks.length);
  };
  const remove = () => {
    if (!current) return;
    onDirty?.();
    setBlocks(blocks.filter((_, i) => i !== selected));
    setSelected(Math.max(0, selected - 1));
  };
  const move = (event: GamepadEvent) => {
    const step: Record<number, [number, number]> = {
      [GamepadButton.DIR_LEFT]: [-1, 0], [GamepadButton.DIR_RIGHT]: [1, 0],
      [GamepadButton.DIR_UP]: [0, -1], [GamepadButton.DIR_DOWN]: [0, 1],
    };
    const delta = step[event.detail.button];
    if (!grabbing || !delta || !current) return;
    event.preventDefault();
    event.stopPropagation();
    update({ x: Math.max(-PANEL_W + 1, Math.min(PANEL_W - 1, current.x + delta[0])), y: Math.max(-PANEL_H + 1, Math.min(PANEL_H - 1, current.y + delta[1])) });
  };

  const label = (block: Block) => {
    if (block.type === "text") return block.text || t("accessories.compose.block.text");
    if (block.type === "metric") return t(`accessories.compose.metric.${block.metric}`);
    if (block.type === "drawing") return drawings.find((d) => d.id === block.drawing)?.name || t("accessories.compose.block.drawing");
    return t(`accessories.compose.block.${block.type}`);
  };

  return (
    <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.lg, padding: theme.space.sm }}>
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, alignItems: "center" }}>
        <PixelPreview decoded={preview} pitch={pitch} animate />
        <Focusable flow-children="row" style={{ display: "flex", gap: 6, maxWidth: PANEL_W * pitch }}>
          <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "clock", x: 4, y: 16, size: "m", color: "aurora" })}><LuClock3 /></DialogButton>
          <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "date", x: 4, y: 4, size: "m", color: "aurora" })}><LuCalendar /></DialogButton>
          <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "text", x: 4, y: 30, size: "m", text: "HOOANDEE", color: "aurora" })}><LuType /></DialogButton>
          <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "metric", x: 4, y: 44, size: "m", metric: "fps", color: "mint" })}><LuGauge /></DialogButton>
          <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "icon", x: 50, y: 4, size: "m", icon: "star", color: "sunset" })}><LuSparkles /></DialogButton>
          {drawings.length > 0 && (
            <DialogButton style={{ minWidth: 0, padding: "8px 10px" }} onClick={() => add({ type: "drawing", x: 40, y: 30, size: "s", drawing: drawings[0].id, color: "aurora" })}><LuImage /></DialogButton>
          )}
        </Focusable>
      </Focusable>
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, width: 240 }}>
        <Focusable style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 170, overflowY: "auto" }}>
          {blocks.map((block, i) => (
            <DialogButton key={i} onClick={() => setSelected(i)}
              style={{ textAlign: "left", padding: "7px 12px", background: i === selected ? theme.color.accent : undefined,
                color: i === selected ? theme.color.onAccent : undefined }}>
              {label(block)}
            </DialogButton>
          ))}
        </Focusable>
        {current && (
          <>
            <Focusable onGamepadDirection={move} onActivate={() => setGrabbing(!grabbing)} onClick={() => setGrabbing(!grabbing)}
              onGamepadBlur={() => setGrabbing(false)}
              style={{ ...theme.card, padding: theme.space.sm, display: "flex", alignItems: "center", gap: 8, justifyContent: "center",
                fontSize: theme.font.caption, color: grabbing ? theme.color.onAccent : theme.color.textMuted,
                background: grabbing ? theme.color.accent : theme.card.background }}>
              <LuMove /> {t(grabbing ? "accessories.compose.moving" : "accessories.compose.move")}
            </Focusable>
            <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
              <DialogButton style={{ minWidth: 0, flex: 1 }} onClick={() => update({ size: next(SIZES, current.size) })}>
                {t(`accessories.compose.size.${current.size}`)}
              </DialogButton>
              <DialogButton style={{ minWidth: 0, flex: 1 }} onClick={() => update({ color: next(COLORS, current.color) })}>
                {t(`accessories.theme.${current.color}`)}
              </DialogButton>
            </Focusable>
            {current.type === "text" && <TextField value={current.text ?? ""} onChange={(e) => update({ text: e.target.value.slice(0, 24) })} />}
            {current.type === "metric" && (
              <DialogButton onClick={() => update({ metric: next(METRICS, current.metric) })}>{t(`accessories.compose.metric.${current.metric}`)}</DialogButton>
            )}
            {current.type === "icon" && (
              <DialogButton onClick={() => update({ icon: next(ICONS, current.icon) })}>{t(`accessories.compose.icon.${current.icon}`)}</DialogButton>
            )}
            {current.type === "drawing" && drawings.length > 1 && (
              <DialogButton onClick={() => update({ drawing: next(drawings.map((d) => d.id), current.drawing) })}>{label(current)}</DialogButton>
            )}
            <DialogButton onClick={remove} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              <LuTrash2 /> {t("accessories.compose.remove")}
            </DialogButton>
          </>
        )}
        <div style={{ flex: 1 }} />
        <DialogButton onClick={() => { onShow(blocks); closeModal?.(); }}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700 }}>
          <LuSend /> {t("accessories.draw.send")}
        </DialogButton>
      </Focusable>
    </Focusable>
  );
};
