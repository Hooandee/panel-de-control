import { DialogButton, Focusable, GamepadButton, GamepadEvent, NavEntryPositionPreferences, TextField } from "@decky/ui";
import { CSSProperties, FC, ReactNode, useEffect, useRef, useState } from "react";
import {
  LuArrowDownToLine, LuArrowUpToLine, LuBlocks, LuCalendar, LuChevronLeft, LuChevronRight, LuClock3, LuCopy, LuGauge, LuImage,
  LuMove, LuPalette, LuRotateCw, LuScaling, LuSend, LuSmile, LuSparkles, LuTrash2, LuType, LuZap,
} from "react-icons/lu";

import { composeAccessoryLayout, DrawingSummary, getAccessoryStickers, listAccessoryDrawings } from "../api";
import { rowChipStyle } from "../components/chipStyle";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { Box, snapMove } from "./composerSnap";
import { DIRECTIONS } from "./DrawEditor";
import { useEditorControls } from "./editorControls";
import { Chip, ChipRow, EditorShell, IconButton, InspectorGroup } from "./EditorShell";
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
type Tab = "pieces" | "edit";

const COLORS = ["aurora", "sunset", "mint", "mono"];
const STICKER_COLORS = ["original", ...COLORS];
const SIZES: Block["size"][] = ["s", "m", "l"];
const FONTS = ["tiny", "small", "bold", "big", "outline", "shadow"];
const METRICS = ["fps", "cpu_pct", "gpu_pct", "ram_pct", "gpu_temp", "cpu_temp", "gpu_w"];
const CATEGORIES: Category[] = ["text", "pills", "stickers", "drawings", "data"];
const MAX_BLOCKS = 30;
const COMPOSE_DELAY_MS = 160;
const GUIDE_MS = 700;
const TILES_PER_ROW = 3;
const CATEGORIES_PER_ROW = 3;

export const STARTER_LAYOUT: Block[] = [
  { type: "date", x: 4, y: 3, size: "m", color: "aurora" },
  { type: "clock", x: 3, y: 13, size: "l", color: "aurora" },
  { type: "sticker", x: 4, y: 40, size: "m", sticker: "heart", color: "original" },
  { type: "metric", x: 22, y: 42, size: "m", metric: "fps", color: "mint" },
];

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });

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
    @keyframes pdcGuide { 0% { opacity: 1; } 100% { opacity: 0; } }
  `;
  doc.head.appendChild(style);
}

interface StickerBook {
  palette: Record<string, number[]>;
  stickers: Record<string, string[][]>;
}

const StickerIcon: FC<{ book: StickerBook; id: string; size?: number; animate?: boolean }> = ({ book, id, size = 30, animate = false }) => {
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

/** A piece in the box: its look on top, its name under it. */
const PieceTile: FC<{ onPick: () => void; label: string; children: ReactNode }> = ({ onPick, label, children }) => (
  <DialogButton onClick={onPick} aria-label={label}
    style={{ flex: "1 1 0", minWidth: 0, width: "auto", height: 62, padding: theme.space.xs, display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 3 }}>
    <span style={{ display: "flex", height: 30, alignItems: "center" }}>{children}</span>
    <span style={{ fontSize: theme.font.caption, fontWeight: 700, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis",
      whiteSpace: "nowrap" }}>{label}</span>
  </DialogButton>
);

const FONT_LOOK: Record<string, CSSProperties> = {
  tiny: { fontSize: 13, fontFamily: "monospace", letterSpacing: 1 },
  small: { fontSize: 16, fontWeight: 600 },
  bold: { fontSize: 16, fontWeight: 900 },
  big: { fontSize: 22, fontWeight: 800 },
  get outline() { return { fontSize: 17, fontWeight: 900, color: "transparent", WebkitTextStroke: `1px ${theme.color.textPrimary}` }; },
  get shadow() { return { fontSize: 17, fontWeight: 800, textShadow: `2px 2px 0 ${theme.pixel.guide}` }; },
};

const swatch = (color: string) => theme.pixel.swatch[color] ?? theme.pixel.swatch.aurora;

export const ComposerBody: FC<{ initial: Block[]; onShow: (blocks: Block[]) => void }> = ({ initial, onShow }) => {
  const { t } = useI18n();
  const { close, leave, markDirty } = useEditorControls();
  const [blocks, setBlocks] = useState<Block[]>(initial.length ? initial : STARTER_LAYOUT);
  const [selected, setSelected] = useState(0);
  const [preview, setPreview] = useState<DecodedFrames | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [boxedBlocks, setBoxedBlocks] = useState<Block[]>([]);
  const [mode, setMode] = useState<Mode>("static");
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const [book, setBook] = useState<StickerBook | null>(null);
  const [grabbing, setGrabbing] = useState(false);
  const [tab, setTab] = useState<Tab>("pieces");
  const [category, setCategory] = useState<Category>("stickers");
  const [guide, setGuide] = useState<{ x: number | null; y: number | null; at: number } | null>(null);
  const placing = useRef<number | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const piecesTab = useRef<HTMLDivElement>(null);

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
  // Hands focus to a control before the one holding it unmounts: Steam has no focus otherwise.
  const focusLater = (target: { current: HTMLElement | null }) => window.setTimeout(() => {
    const control = target.current?.querySelector<HTMLElement>(".Focusable, button") ?? target.current;
    if (control) navigation.focus(control);
  }, 0);

  const change = (list: Block[]) => {
    markDirty();
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
    // The new piece is picked up on the panel, ready to be moved with the d-pad.
    if (stage.current) navigation.focus(stage.current);
    setGrabbing(true);
    setTab("edit");
  };
  const remove = () => {
    if (!current) return;
    const left = blocks.filter((_, i) => i !== selected);
    change(left);
    setSelected(Math.max(0, Math.min(selected, left.length - 1)));
    setGrabbing(false);
    if (!left.length) {
      setTab("pieces");
      focusLater(piecesTab);
    }
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
  const pick = (step: number) => {
    if (!blocks.length) return;
    setSelected((selected + step + blocks.length) % blocks.length);
    setTab("edit");
  };
  const show = () => {
    onShow(blocks);
    close();
  };

  const liveBoxes: Box[] = blocks.map((block, i) => {
    const known = boxes[i];
    if (!known) return { x: block.x, y: block.y, w: 6, h: 6 };
    const turn = swapped(block, boxedBlocks[i]);
    return { x: block.x, y: block.y, w: turn ? known.h : known.w, h: turn ? known.w : known.h };
  });

  const onStageButton = (event: GamepadEvent) => {
    const button = event.detail.button;
    if (button !== GamepadButton.BUMPER_LEFT && button !== GamepadButton.BUMPER_RIGHT) return;
    event.preventDefault();
    event.stopPropagation();
    pick(button === GamepadButton.BUMPER_RIGHT ? 1 : -1);
  };
  const move = (event: GamepadEvent) => {
    const delta = DIRECTIONS[event.detail.button];
    if (!grabbing || !delta || !current) return;
    event.preventDefault();
    event.stopPropagation();
    const snapped = snapMove(liveBoxes, selected, delta[0], delta[1]);
    if (snapped.guideX !== null || snapped.guideY !== null) setGuide({ x: snapped.guideX, y: snapped.guideY, at: Date.now() });
    update({ x: snapped.x, y: snapped.y });
  };
  const stopGrab = (event: GamepadEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setGrabbing(false);
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

  const renderStage = (pitch: number) => {
    const width = PANEL_W * pitch;
    const height = PANEL_H * pitch;
    // Pieces may hang off an edge on purpose; the selection frame marks only the part on the panel.
    const held = liveBoxes[selected];
    const box = held && (() => {
      const x0 = Math.max(0, held.x), y0 = Math.max(0, held.y);
      const x1 = Math.min(PANEL_W, held.x + held.w), y1 = Math.min(PANEL_H, held.y + held.h);
      return x1 > x0 && y1 > y0 ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
    })();
    const showGuide = guide && Date.now() - guide.at < GUIDE_MS ? guide : null;
    return (
      // Steam hands every d-pad press to a Focusable that has a direction handler, so the panel only
      // takes them while a piece is held; otherwise the d-pad moves on to the rest of the editor.
      <Focusable ref={stage} onActivate={() => current && setGrabbing(!grabbing)} onClick={() => current && setGrabbing(!grabbing)}
        onGamepadDirection={grabbing ? move : undefined} onButtonDown={grabbing ? onStageButton : undefined}
        onGamepadBlur={() => setGrabbing(false)}
        onSecondaryButton={() => { if (current) rotate(); }} onSecondaryActionDescription={t("accessories.compose.rotate")}
        onOptionsButton={duplicate} onOptionsActionDescription={t("accessories.compose.duplicate")}
        onMenuButton={show} onMenuActionDescription={t("accessories.draw.send")}
        onCancelButton={grabbing ? stopGrab : undefined} onCancelActionDescription={grabbing ? t("accessories.compose.drop") : undefined}
        onOKActionDescription={t(grabbing ? "accessories.compose.drop" : "accessories.compose.grab")}
        style={{ position: "relative", width, height, borderRadius: theme.radius.md, flex: "0 0 auto" }}>
        <PixelPreview decoded={preview} pitch={pitch} animate />
        {box && (
          <div style={{ position: "absolute", left: box.x * pitch, top: box.y * pitch, width: box.w * pitch,
            height: box.h * pitch, boxSizing: "border-box", borderRadius: theme.radius.sm, pointerEvents: "none",
            border: `2px ${grabbing ? "solid" : "dashed"} ${grabbing ? theme.color.accent : theme.color.textPrimary}`,
            boxShadow: grabbing ? `0 0 18px rgba(${theme.color.accentRgb},0.65)` : "none",
            animation: grabbing ? "none" : "pdcPulse 1.4s ease-in-out infinite",
            transition: "left 70ms ease, top 70ms ease, width 120ms ease, height 120ms ease" }} />
        )}
        {showGuide && showGuide.x !== null && (
          <div key={`gx${showGuide.at}`} style={{ position: "absolute", left: showGuide.x * pitch + pitch / 2 - 1, top: 0, width: 2, height,
            background: theme.pixel.guide, animation: `pdcGuide ${GUIDE_MS}ms ease-out forwards`, pointerEvents: "none" }} />
        )}
        {showGuide && showGuide.y !== null && (
          <div key={`gy${showGuide.at}`} style={{ position: "absolute", top: showGuide.y * pitch + pitch / 2 - 1, left: 0, height: 2, width,
            background: theme.pixel.guide, animation: `pdcGuide ${GUIDE_MS}ms ease-out forwards`, pointerEvents: "none" }} />
        )}
        <span style={{ position: "absolute", right: theme.space.sm, top: theme.space.sm, ...rowChipStyle(false), padding: "3px 9px",
          fontWeight: 800, pointerEvents: "none" }}>
          {mode === "live" ? <LuGauge size={11} /> : mode === "clock" ? <LuClock3 size={11} /> : mode === "animated" ? <LuSparkles size={11} /> : <LuImage size={11} />}
          {t(`accessories.compose.mode.${mode}`)}
        </span>
      </Focusable>
    );
  };

  const navigator = (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: theme.space.xs, justifyContent: "center" }}>
        <IconButton label={t("accessories.compose.prevPiece")} onPress={() => pick(-1)} disabled={blocks.length < 2}><LuChevronLeft /></IconButton>
        <span style={{ display: "flex", alignItems: "center", gap: theme.space.sm, minWidth: 0, maxWidth: 320, fontSize: theme.font.body,
          fontWeight: 700, color: theme.color.textPrimary }}>
          {current ? typeIcon(current) : <LuBlocks />}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {current ? label(current) : t("accessories.compose.empty")}
          </span>
          {current && <span style={{ color: theme.color.textMuted, fontWeight: 600, whiteSpace: "nowrap" }}>
            {t("accessories.compose.pieceOf", { n: selected + 1, total: blocks.length })}
          </span>}
        </span>
        <IconButton label={t("accessories.compose.nextPiece")} onPress={() => pick(1)} disabled={blocks.length < 2}><LuChevronRight /></IconButton>
      </Focusable>
      <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs, fontSize: theme.font.caption,
        color: grabbing ? theme.color.accent : theme.color.textMuted, fontWeight: 650 }}>
        <LuMove /> {t(grabbing ? "accessories.compose.moving" : "accessories.compose.move")}
      </span>
    </div>
  );

  const tiles = (): ReactNode[] => {
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
          <span style={{ padding: "3px 10px", borderRadius: theme.radius.lg, background: swatch(color), color: theme.pixel.onSwatch,
            fontSize: theme.font.caption, fontWeight: 900 }}>GG</span>
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

  const box = tiles();
  const piecesPanel = (
    <>
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        {chunk(CATEGORIES, CATEGORIES_PER_ROW).map((row, r) => (
          <ChipRow key={r}>
            {row.map((name) => (
              <Chip key={name} active={category === name} label={t(`accessories.compose.cat.${name}`)} onPick={() => setCategory(name)} />
            ))}
            {row.length < CATEGORIES_PER_ROW && <div style={{ flex: CATEGORIES_PER_ROW - row.length }} />}
          </ChipRow>
        ))}
      </Focusable>
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        {chunk(box, TILES_PER_ROW).map((row, r) => (
          <Focusable key={r} flow-children="row" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_X} style={{ display: "flex", gap: theme.space.xs }}>
            {row}
            {row.length < TILES_PER_ROW && <div style={{ flex: TILES_PER_ROW - row.length }} />}
          </Focusable>
        ))}
        {!box.length && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.compose.noDrawings")}</span>}
      </Focusable>
    </>
  );

  const editPanel = current ? (
    <>
      <InspectorGroup label={t("accessories.compose.look")}>
        <ChipRow>
          <Chip active={false} icon={<LuScaling />} label={t(`accessories.compose.size.${current.size}`)} onPick={() => update({ size: next(SIZES, current.size) })} />
          <Chip active={false} icon={<span style={{ width: 16, height: 16, borderRadius: theme.radius.sm, background: swatch(current.color) }} />}
            label={t(`accessories.theme.${current.color}`)}
            onPick={() => update({ color: next(current.type === "sticker" ? STICKER_COLORS : COLORS, current.color) })} />
        </ChipRow>
        <ChipRow>
          <Chip active={false} icon={<LuRotateCw />} label={t("accessories.compose.rotate")} onPick={rotate} />
          {hasFont(current) && (
            <Chip active={false} icon={<LuPalette />} label={t(`accessories.compose.font.${current.font ?? "small"}`)}
              onPick={() => update({ font: next(FONTS, current.font ?? "small") })} />
          )}
        </ChipRow>
        {(current.type === "text" || current.type === "pill") && (
          <TextField value={current.text ?? ""} onChange={(e) => update({ text: e.target.value.slice(0, 24) })} />
        )}
        {current.type === "metric" && (
          <Chip active={false} icon={<LuGauge />} label={t(`accessories.compose.metric.${current.metric}`)} onPick={() => update({ metric: next(METRICS, current.metric) })} />
        )}
        {current.type === "sticker" && book && (
          <Chip active={false} icon={current.sticker ? <StickerIcon book={book} id={current.sticker} size={18} /> : <LuSmile />}
            label={t("accessories.compose.otherSticker")} onPick={() => update({ sticker: next(Object.keys(book.stickers), current.sticker) })} />
        )}
        {current.type === "drawing" && drawings.length > 1 && (
          <Chip active={false} icon={<LuImage />} label={label(current)} onPick={() => update({ drawing: next(drawings.map((d) => d.id), current.drawing) })} />
        )}
      </InspectorGroup>
      <InspectorGroup label={t("accessories.compose.arrange")}>
        <ChipRow>
          <Chip active={false} icon={<LuArrowUpToLine />} label={t("accessories.compose.forward")} onPick={() => layer(1)} />
          <Chip active={false} icon={<LuArrowDownToLine />} label={t("accessories.compose.backward")} onPick={() => layer(-1)} />
        </ChipRow>
        <ChipRow>
          <Chip active={false} icon={<LuCopy />} label={t("accessories.compose.duplicate")} onPick={duplicate} />
          <Chip active={false} icon={<LuTrash2 />} label={t("accessories.compose.remove")} onPick={remove} />
        </ChipRow>
      </InspectorGroup>
    </>
  ) : (
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.compose.empty")}</span>
  );

  const inspector = (
    <>
      <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.xs }}>
        {(["pieces", "edit"] as const).map((name) => (
          <div key={name} ref={name === "pieces" ? piecesTab : undefined} style={{ flex: 1, display: "flex" }}>
            <Chip active={tab === name} label={t(`accessories.compose.tab.${name}`)} onPick={() => setTab(name)} />
          </div>
        ))}
      </Focusable>
      {tab === "pieces" ? piecesPanel : editPanel}
    </>
  );

  return (
    <EditorShell icon={<LuBlocks size={22} />} title={t("accessories.compose.title")} stage={renderStage} stageFooter={navigator}
      inspector={inspector} primaryLabel={t("accessories.draw.send")} primaryIcon={<LuSend />} onPrimary={show} onClose={leave} />
  );
};
