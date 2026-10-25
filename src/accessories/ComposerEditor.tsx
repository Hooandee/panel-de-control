import { DialogButton, Focusable, GamepadButton, GamepadEvent, TextField } from "@decky/ui";
import { CSSProperties, FC, ReactNode, useEffect, useRef, useState } from "react";
import {
  LuArrowDownToLine, LuArrowUpToLine, LuCalendar, LuClock3, LuCopy, LuGauge, LuImage, LuMove, LuPalette, LuRotateCw,
  LuScaling, LuSend, LuSmile, LuSparkles, LuTrash2, LuType, LuZap,
} from "react-icons/lu";

import { composeAccessoryLayout, DrawingSummary, getAccessoryStickers, listAccessoryDrawings } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Box, snapMove } from "./composerSnap";
import { decodeFrames, DecodedFrames, PANEL_H, PANEL_W } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";

export interface Block {
  type: "clock" | "date" | "text" | "metric" | "icon" | "drawing" | "pill" | "sticker";
  x: number;
  y: number;
  size: "s" | "m" | "l";
  color: string;
  rot?: 0 | 90 | 180 | 270;
  font?: string;
  text?: string;
  metric?: string;
  icon?: string;
  sticker?: string;
  drawing?: string;
}

type Mode = "static" | "animated" | "clock" | "live";
type Category = "text" | "pills" | "stickers" | "drawings" | "data";

const COLORS = ["aurora", "sunset", "mint", "mono"];
const STICKER_COLORS = ["original", ...COLORS];
const SIZES: Block["size"][] = ["s", "m", "l"];
const FONTS = ["tiny", "small", "bold", "big", "outline", "shadow"];
const METRICS = ["fps", "cpu_pct", "gpu_pct", "ram_pct", "gpu_temp", "cpu_temp", "gpu_w"];
const CATEGORIES: Category[] = ["text", "pills", "stickers", "drawings", "data"];
const MAX_BLOCKS = 30;
const COMPOSE_DELAY_MS = 160;
const GUIDE_MS = 700;
const ROW = 3;

export const STARTER_LAYOUT: Block[] = [
  { type: "date", x: 4, y: 3, size: "m", color: "aurora" },
  { type: "clock", x: 3, y: 13, size: "l", color: "aurora" },
  { type: "sticker", x: 4, y: 40, size: "m", sticker: "heart", color: "original" },
  { type: "metric", x: 22, y: 42, size: "m", metric: "fps", color: "mint" },
];

const next = <T,>(list: T[], value: T | undefined): T => list[(list.indexOf(value as T) + 1) % list.length];
const chunk = <T,>(list: T[], size: number): T[][] =>
  Array.from({ length: Math.ceil(list.length / size) }, (_, i) => list.slice(i * size, i * size + size));
const hasFont = (block: Block) => ["text", "pill", "clock", "date", "metric"].includes(block.type);
const swapped = (a: Block | undefined, b: Block | undefined) => ((a?.rot ?? 0) - (b?.rot ?? 0)) % 180 !== 0;

const STYLE_ID = "pdc-composer-style";
function ensureStyle(doc: Document) {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    @keyframes pdcPulse { 0%,100% { opacity: 1; } 50% { opacity: .45; } }
    @keyframes pdcPop { 0% { transform: scale(.6); opacity: 0; } 70% { transform: scale(1.12); opacity: 1; } 100% { transform: scale(1); } }
    @keyframes pdcGuide { 0% { opacity: 1; } 100% { opacity: 0; } }
  `;
  doc.head.appendChild(style);
}

interface StickerBook {
  palette: Record<string, number[]>;
  stickers: Record<string, string[][]>;
}

const StickerIcon: FC<{ book: StickerBook; id: string; size?: number; animate?: boolean }> = ({ book, id, size = 34, animate = false }) => {
  const canvas = useRef<HTMLCanvasElement>(null);
  const frames = book.stickers[id] ?? [];
  useEffect(() => {
    let frame = 0;
    const draw = () => {
      const ctx = canvas.current?.getContext("2d");
      const rows = frames[frame % Math.max(1, frames.length)];
      if (!ctx || !rows) return;
      const width = Math.max(...rows.map((row) => row.length));
      const cell = Math.floor(size / Math.max(width, rows.length));
      const ox = Math.floor((size - width * cell) / 2);
      const oy = Math.floor((size - rows.length * cell) / 2);
      ctx.clearRect(0, 0, size, size);
      rows.forEach((row, y) => [...row].forEach((ch, x) => {
        const rgb = book.palette[ch];
        if (!rgb) return;
        ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
        ctx.fillRect(ox + x * cell, oy + y * cell, cell - (cell > 3 ? 1 : 0), cell - (cell > 3 ? 1 : 0));
      }));
    };
    draw();
    if (!animate || frames.length < 2) return undefined;
    const timer = window.setInterval(() => { frame += 1; draw(); }, 160);
    return () => window.clearInterval(timer);
  }, [id, animate, size, frames.length]);
  return <canvas ref={canvas} width={size} height={size} style={{ width: size, height: size, imageRendering: "pixelated" }} />;
};

const PieceTile: FC<{ onPick: () => void; label: string; children: ReactNode }> = ({ onPick, label, children }) => {
  const [focused, setFocused] = useState(false);
  return (
    <Focusable onActivate={onPick} onClick={onPick} onGamepadFocus={() => setFocused(true)} onGamepadBlur={() => setFocused(false)}
      aria-label={label}
      style={{ flex: 1, minWidth: 0, height: 58, borderRadius: theme.radius.md, display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", gap: 3, background: focused ? `rgba(${theme.color.accentRgb},0.22)` : "rgba(255,255,255,0.05)",
        boxShadow: focused ? `inset 0 0 0 2px ${theme.color.accent}, 0 4px 14px rgba(0,0,0,0.4)` : "inset 0 0 0 1px rgba(255,255,255,0.06)",
        transform: focused ? "scale(1.07)" : "scale(1)", transition: "transform 110ms ease, box-shadow 110ms ease, background 110ms ease" }}>
      {children}
      <span style={{ fontSize: 9, fontWeight: 700, color: focused ? theme.color.textPrimary : theme.color.textMuted, maxWidth: "100%",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
    </Focusable>
  );
};

const FONT_LOOK: Record<string, CSSProperties> = {
  tiny: { fontSize: 13, fontFamily: "monospace", letterSpacing: 1 },
  small: { fontSize: 16, fontWeight: 600 },
  bold: { fontSize: 16, fontWeight: 900 },
  big: { fontSize: 22, fontWeight: 800 },
  outline: { fontSize: 17, fontWeight: 900, color: "transparent", WebkitTextStroke: "1px #fff" },
  shadow: { fontSize: 17, fontWeight: 800, textShadow: "2px 2px 0 rgba(64,220,255,0.45)" },
};

const SWATCH: Record<string, string> = {
  aurora: "linear-gradient(90deg,#b078ff,#40dcff)", sunset: "linear-gradient(90deg,#ff963c,#ff4678)",
  mint: "linear-gradient(90deg,#5af0aa,#3caaff)", mono: "linear-gradient(90deg,#ebe8fa,#c8c4e1)",
  ledbar: "linear-gradient(90deg,#ff71ce,#01cdfe)", original: "conic-gradient(#ff5a6e,#ffd23c,#5ae66e,#3c78ff,#aa64ff,#ff5a6e)",
};

const ToolButton: FC<{ icon: ReactNode; label: string; onPress: () => void; danger?: boolean }> = ({ icon, label, onPress, danger }) => (
  <DialogButton onClick={onPress} onOKButton={onPress}
    style={{ flex: 1, minWidth: 0, padding: "7px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 3, fontSize: 10,
      fontWeight: 700, color: danger ? theme.color.warn : undefined }}>
    <span style={{ display: "flex", fontSize: 16 }}>{icon}</span>
    {label}
  </DialogButton>
);

export const ComposerBody: FC<{ pitch?: number; onDirty?: () => void; initial: Block[]; onShow: (blocks: Block[]) => void; closeModal?: () => void }> = ({ initial, onShow, closeModal, onDirty, pitch = 6 }) => {
  const { t } = useI18n();
  const [blocks, setBlocks] = useState<Block[]>(initial.length ? initial : STARTER_LAYOUT);
  const [selected, setSelected] = useState(0);
  const [preview, setPreview] = useState<DecodedFrames | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [boxedBlocks, setBoxedBlocks] = useState<Block[]>([]);
  const [mode, setMode] = useState<Mode>("static");
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const [book, setBook] = useState<StickerBook | null>(null);
  const [grabbing, setGrabbing] = useState(false);
  const [tab, setTab] = useState<"pieces" | "edit">("pieces");
  const [category, setCategory] = useState<Category>("stickers");
  const [guide, setGuide] = useState<{ x: number | null; y: number | null; at: number } | null>(null);
  const placing = useRef<number | null>(null);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (stage.current) ensureStyle(stage.current.ownerDocument);
    void listAccessoryDrawings().then((result) => setDrawings(result?.drawings ?? [])).catch(() => setDrawings([]));
    void getAccessoryStickers().then((result) => { if (result?.stickers) setBook(result); }).catch(() => undefined);
  }, []);

  useEffect(() => {
    let live = true;
    const place = placing.current;
    const timer = window.setTimeout(() => {
      void composeAccessoryLayout({ blocks }, place)
        .then((result) => {
          if (!live || !result || result.ok === false) return;
          setPreview(decodeFrames(result));
          setBoxes(result.boxes);
          setMode(result.mode);
          const adopted = (place !== null ? result.blocks : blocks) as unknown as Block[];
          setBoxedBlocks(adopted);
          if (place !== null) {
            placing.current = null;
            setBlocks(adopted);
          }
        })
        .catch(() => undefined);
    }, place !== null ? 0 : COMPOSE_DELAY_MS);
    return () => { live = false; window.clearTimeout(timer); };
  }, [JSON.stringify(blocks)]);

  const current = blocks[selected];
  const change = (list: Block[]) => {
    onDirty?.();
    setBlocks(list);
  };
  const update = (patch: Partial<Block>) => {
    if (current) change(blocks.map((block, i) => (i === selected ? { ...block, ...patch } : block)));
  };
  const add = (block: Block) => {
    if (blocks.length >= MAX_BLOCKS) return;
    placing.current = blocks.length;
    change([...blocks, block]);
    setSelected(blocks.length);
    setTab("edit");
  };
  const remove = () => {
    if (!current) return;
    change(blocks.filter((_, i) => i !== selected));
    setSelected(Math.max(0, selected - 1));
    setGrabbing(false);
  };
  const duplicate = () => {
    if (!current || blocks.length >= MAX_BLOCKS) return;
    placing.current = blocks.length;
    change([...blocks, { ...current }]);
    setSelected(blocks.length);
  };
  const layer = (step: number) => {
    const target = selected + step;
    if (!current || target < 0 || target >= blocks.length) return;
    const list = [...blocks];
    [list[selected], list[target]] = [list[target], list[selected]];
    change(list);
    setSelected(target);
  };
  const rotate = () => update({ rot: (((current?.rot ?? 0) + 90) % 360) as Block["rot"] });

  const liveBoxes: Box[] = blocks.map((block, i) => {
    const known = boxes[i];
    if (!known) return { x: block.x, y: block.y, w: 6, h: 6 };
    const turn = swapped(block, boxedBlocks[i]);
    return { x: block.x, y: block.y, w: turn ? known.h : known.w, h: turn ? known.w : known.h };
  });

  const onStageButton = (event: GamepadEvent) => {
    const button = event.detail.button;
    if (button !== GamepadButton.BUMPER_LEFT && button !== GamepadButton.BUMPER_RIGHT) return;
    if (!blocks.length) return;
    event.preventDefault();
    event.stopPropagation();
    setSelected((selected + (button === GamepadButton.BUMPER_RIGHT ? 1 : blocks.length - 1)) % blocks.length);
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
    const snapped = snapMove(liveBoxes, selected, delta[0], delta[1]);
    if (snapped.guideX !== null || snapped.guideY !== null) setGuide({ x: snapped.guideX, y: snapped.guideY, at: Date.now() });
    update({ x: snapped.x, y: snapped.y });
  };

  const label = (block: Block) => {
    if (block.type === "text" || block.type === "pill") return block.text || t(`accessories.compose.block.${block.type}`);
    if (block.type === "metric") return t(`accessories.compose.metric.${block.metric}`);
    if (block.type === "drawing") return drawings.find((d) => d.id === block.drawing)?.name || t("accessories.compose.block.drawing");
    return t(`accessories.compose.block.${block.type}`);
  };
  const typeIcon = (block: Block): ReactNode => ({
    clock: <LuClock3 />, date: <LuCalendar />, text: <LuType />, pill: <LuType />, metric: <LuGauge />, icon: <LuSmile />,
    sticker: <LuSmile />, drawing: <LuImage />,
  })[block.type];

  const width = PANEL_W * pitch;
  const height = PANEL_H * pitch;
  const box = liveBoxes[selected];
  const showGuide = guide && Date.now() - guide.at < GUIDE_MS ? guide : null;

  const pieces = (): ReactNode[] => {
    if (category === "text") {
      return FONTS.map((font) => (
        <PieceTile key={font} label={t(`accessories.compose.font.${font}`)}
          onPick={() => add({ type: "text", x: 0, y: 0, size: "m", font, text: t("accessories.compose.sample"), color: "aurora" })}>
          <span style={{ ...FONT_LOOK[font], color: FONT_LOOK[font].color ?? theme.color.textPrimary, lineHeight: 1 }}>Aa</span>
        </PieceTile>
      ));
    }
    if (category === "pills") {
      return COLORS.map((color) => (
        <PieceTile key={color} label={t(`accessories.theme.${color}`)}
          onPick={() => add({ type: "pill", x: 0, y: 0, size: "m", font: "small", text: "GG", color })}>
          <span style={{ padding: "3px 10px", borderRadius: 999, background: SWATCH[color], color: "#140f1e", fontSize: 11, fontWeight: 900 }}>GG</span>
        </PieceTile>
      ));
    }
    if (category === "stickers") {
      return book ? Object.keys(book.stickers).map((id) => (
        <PieceTile key={id} label={t(`accessories.sticker.${id}`)} onPick={() => add({ type: "sticker", x: 0, y: 0, size: "m", sticker: id, color: "original" })}>
          <StickerIcon book={book} id={id} animate />
        </PieceTile>
      )) : [];
    }
    if (category === "drawings") {
      return drawings.map((drawing) => (
        <PieceTile key={drawing.id} label={drawing.name || t("accessories.compose.block.drawing")}
          onPick={() => add({ type: "drawing", x: 0, y: 0, size: "s", drawing: drawing.id, color: "aurora" })}>
          <LuImage size={22} color={theme.color.accent} />
        </PieceTile>
      ));
    }
    return [
      <PieceTile key="clock" label={t("accessories.compose.block.clock")} onPick={() => add({ type: "clock", x: 0, y: 0, size: "l", color: "aurora" })}><LuClock3 size={22} /></PieceTile>,
      <PieceTile key="date" label={t("accessories.compose.block.date")} onPick={() => add({ type: "date", x: 0, y: 0, size: "m", color: "aurora" })}><LuCalendar size={22} /></PieceTile>,
      ...METRICS.map((metric) => (
        <PieceTile key={metric} label={t(`accessories.compose.metric.${metric}`)}
          onPick={() => add({ type: "metric", x: 0, y: 0, size: "m", metric, color: "mint" })}>
          {metric === "gpu_w" ? <LuZap size={22} /> : <LuGauge size={22} />}
        </PieceTile>
      )),
    ];
  };
  const tiles = pieces();
  const stopGrab = (event: GamepadEvent) => {
    event.stopPropagation();
    setGrabbing(false);
  };

  return (
    <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.lg, padding: theme.space.sm }}>
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <Focusable onActivate={() => current && setGrabbing(!grabbing)} onClick={() => current && setGrabbing(!grabbing)}
          onGamepadDirection={move} onButtonDown={onStageButton} onGamepadBlur={() => setGrabbing(false)}
          onSecondaryButton={() => { if (current) rotate(); }} onSecondaryActionDescription={t("accessories.compose.rotate")}
          onOptionsButton={duplicate} onOptionsActionDescription={t("accessories.compose.duplicate")}
          onCancelButton={grabbing ? stopGrab : undefined}
          onOKActionDescription={t(grabbing ? "accessories.compose.drop" : "accessories.compose.grab")}
          style={{ position: "relative", borderRadius: theme.radius.md }}>
          <div ref={stage} style={{ position: "relative", width, height }}>
            <PixelPreview decoded={preview} pitch={pitch} animate />
            {box && (
              <div style={{ position: "absolute", left: box.x * pitch - 3, top: box.y * pitch - 3, width: box.w * pitch + 6,
                height: box.h * pitch + 6, borderRadius: 6, pointerEvents: "none",
                border: `2px ${grabbing ? "solid" : "dashed"} ${grabbing ? theme.color.accent : "rgba(255,255,255,0.8)"}`,
                boxShadow: grabbing ? `0 0 18px rgba(${theme.color.accentRgb},0.65)` : "none",
                animation: grabbing ? "none" : "pdcPulse 1.4s ease-in-out infinite",
                transition: "left 70ms ease, top 70ms ease, width 120ms ease, height 120ms ease" }} />
            )}
            {showGuide && showGuide.x !== null && (
              <div key={`gx${showGuide.at}`} style={{ position: "absolute", left: showGuide.x * pitch + pitch / 2 - 1, top: 0, width: 2, height,
                background: "#40dcff", boxShadow: "0 0 10px #40dcff", animation: `pdcGuide ${GUIDE_MS}ms ease-out forwards`, pointerEvents: "none" }} />
            )}
            {showGuide && showGuide.y !== null && (
              <div key={`gy${showGuide.at}`} style={{ position: "absolute", top: showGuide.y * pitch + pitch / 2 - 1, left: 0, height: 2, width,
                background: "#40dcff", boxShadow: "0 0 10px #40dcff", animation: `pdcGuide ${GUIDE_MS}ms ease-out forwards`, pointerEvents: "none" }} />
            )}
            <span style={{ position: "absolute", right: 8, top: 8, padding: "3px 9px", borderRadius: 999, fontSize: 10, fontWeight: 800,
              letterSpacing: 0.4, textTransform: "uppercase", background: "rgba(10,9,11,0.78)", color: theme.color.textPrimary,
              display: "flex", alignItems: "center", gap: 5 }}>
              {mode === "live" ? <LuGauge size={11} /> : mode === "clock" ? <LuClock3 size={11} /> : mode === "animated" ? <LuSparkles size={11} /> : <LuImage size={11} />}
              {t(`accessories.compose.mode.${mode}`)}
            </span>
          </div>
          <div style={{ marginTop: 6, fontSize: theme.font.caption, color: grabbing ? theme.color.accent : theme.color.textMuted,
            display: "flex", alignItems: "center", gap: 6, fontWeight: 650 }}>
            <LuMove /> {t(grabbing ? "accessories.compose.moving" : "accessories.compose.move")}
          </div>
        </Focusable>
        <Focusable flow-children="row" style={{ display: "flex", gap: 6, maxWidth: width, overflowX: "auto", paddingBottom: 4 }}>
          {blocks.map((block, i) => (
            <DialogButton key={i} onClick={() => { setSelected(i); setTab("edit"); }} onOKButton={() => { setSelected(i); setTab("edit"); }}
              style={{ flex: "0 0 auto", minWidth: 0, padding: "6px 10px", display: "flex", alignItems: "center", gap: 6, fontSize: 11,
                fontWeight: 700, maxWidth: 140, background: i === selected ? theme.color.accent : undefined,
                color: i === selected ? theme.color.onAccent : undefined, animation: "pdcPop 260ms ease-out" }}>
              {typeIcon(block)}
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label(block)}</span>
            </DialogButton>
          ))}
          {!blocks.length && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.compose.empty")}</span>}
        </Focusable>
      </Focusable>

      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, width: 220 }}>
        <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
          {(["pieces", "edit"] as const).map((name) => (
            <DialogButton key={name} onClick={() => setTab(name)} onOKButton={() => setTab(name)}
              style={{ flex: 1, minWidth: 0, fontWeight: 800, background: tab === name ? theme.color.accent : undefined,
                color: tab === name ? theme.color.onAccent : undefined }}>
              {t(`accessories.compose.tab.${name}`)}
            </DialogButton>
          ))}
        </Focusable>

        {tab === "pieces" && (
          <>
            <Focusable flow-children="row" style={{ display: "flex", gap: 4, overflowX: "auto" }}>
              {CATEGORIES.map((name) => (
                <DialogButton key={name} onClick={() => setCategory(name)} onOKButton={() => setCategory(name)}
                  style={{ flex: "0 0 auto", minWidth: 0, padding: "5px 11px", fontSize: 11, fontWeight: 800, borderRadius: 999,
                    background: category === name ? "rgba(255,255,255,0.92)" : "rgba(255,255,255,0.06)",
                    color: category === name ? "#140f1e" : theme.color.textPrimary }}>
                  {t(`accessories.compose.cat.${name}`)}
                </DialogButton>
              ))}
            </Focusable>
            <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 210, overflowY: "auto", padding: 4 }}>
              {chunk(tiles, ROW).map((row, r) => (
                <Focusable key={r} flow-children="row" style={{ display: "flex", gap: 6 }}>
                  {row}
                  {row.length < ROW && Array.from({ length: ROW - row.length }, (_, k) => <div key={`pad${k}`} style={{ flex: 1 }} />)}
                </Focusable>
              ))}
              {!tiles.length && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.compose.noDrawings")}</span>}
            </Focusable>
          </>
        )}

        {tab === "edit" && current && (
          <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 800, color: theme.color.textPrimary }}>
              {current.type === "sticker" && book && current.sticker ? <StickerIcon book={book} id={current.sticker} size={26} animate /> : typeIcon(current)}
              {label(current)}
            </div>
            <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
              <ToolButton icon={<LuRotateCw />} label={t("accessories.compose.rotate")} onPress={rotate} />
              <ToolButton icon={<LuScaling />} label={t(`accessories.compose.size.${current.size}`)} onPress={() => update({ size: next(SIZES, current.size) })} />
              <ToolButton icon={<span style={{ width: 16, height: 16, borderRadius: 8, background: SWATCH[current.color] ?? SWATCH.aurora }} />}
                label={t(`accessories.theme.${current.color}`)}
                onPress={() => update({ color: next(current.type === "sticker" ? STICKER_COLORS : COLORS, current.color) })} />
              {hasFont(current) && (
                <ToolButton icon={<LuPalette />} label={t(`accessories.compose.font.${current.font ?? "small"}`)}
                  onPress={() => update({ font: next(FONTS, current.font ?? "small") })} />
              )}
            </Focusable>
            {(current.type === "text" || current.type === "pill") && (
              <TextField value={current.text ?? ""} onChange={(e) => update({ text: e.target.value.slice(0, 24) })} />
            )}
            {current.type === "metric" && (
              <DialogButton onClick={() => update({ metric: next(METRICS, current.metric) })}>{t(`accessories.compose.metric.${current.metric}`)}</DialogButton>
            )}
            {current.type === "sticker" && book && (
              <DialogButton onClick={() => update({ sticker: next(Object.keys(book.stickers), current.sticker) })}
                style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                <LuSmile /> {t("accessories.compose.otherSticker")}
              </DialogButton>
            )}
            {current.type === "drawing" && drawings.length > 1 && (
              <DialogButton onClick={() => update({ drawing: next(drawings.map((d) => d.id), current.drawing) })}>{label(current)}</DialogButton>
            )}
            <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
              <ToolButton icon={<LuCopy />} label={t("accessories.compose.duplicate")} onPress={duplicate} />
              <ToolButton icon={<LuArrowUpToLine />} label={t("accessories.compose.forward")} onPress={() => layer(1)} />
              <ToolButton icon={<LuArrowDownToLine />} label={t("accessories.compose.backward")} onPress={() => layer(-1)} />
              <ToolButton icon={<LuTrash2 />} label={t("accessories.compose.remove")} onPress={remove} danger />
            </Focusable>
          </Focusable>
        )}
        {tab === "edit" && !current && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.compose.empty")}</span>}

        <div style={{ flex: 1 }} />
        <DialogButton onClick={() => { onShow(blocks); closeModal?.(); }}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 800 }}>
          <LuSend /> {t("accessories.draw.send")}
        </DialogButton>
      </Focusable>
    </Focusable>
  );
};
