import { Focusable, GamepadButton, GamepadEvent, NavEntryPositionPreferences, TextField } from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import {
  LuChevronLeft, LuChevronRight, LuCopy, LuEraser, LuFlipHorizontal2, LuLayers, LuPaintBucket, LuPencil, LuPlus, LuSend, LuTrash2, LuUndo2,
} from "react-icons/lu";

import { saveAccessoryDrawing } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { blankFrame, DRAW_PALETTE, encodeFrame, fill, getPixel, paint, Rgb } from "./drawing";
import { useEditorControls } from "./editorControls";
import { Chip, ChipRow, EditorShell, IconButton, InspectorGroup, useLive } from "./EditorShell";
import { PANEL_H, PANEL_W } from "./pixelFrames";

const MAX_FRAMES = 48;
const UNDO_STEPS = 30;
const SPEEDS = [4, 8, 12];
const SWATCHES_PER_ROW = 4;
type Tool = "pencil" | "eraser" | "fill";

export interface DrawingDraft {
  id?: string;
  name: string;
  frames: Uint8Array[];
  fps: number;
}

export const DIRECTIONS: Record<number, [number, number]> = {
  [GamepadButton.DIR_LEFT]: [-1, 0], [GamepadButton.DIR_RIGHT]: [1, 0],
  [GamepadButton.DIR_UP]: [0, -1], [GamepadButton.DIR_DOWN]: [0, 1],
};

const sameColour = (a: Rgb, b: Rgb) => a.every((v, k) => v === b[k]);

function drawCanvas(ctx: CanvasRenderingContext2D, frame: Uint8Array, onion: Uint8Array | null, cursor: [number, number] | null, pitch: number) {
  ctx.fillStyle = theme.pixel.face;
  ctx.fillRect(0, 0, PANEL_W * pitch, PANEL_H * pitch);
  const gap = pitch >= 4 ? 1 : 0;
  for (let y = 0; y < PANEL_H; y += 1) {
    for (let x = 0; x < PANEL_W; x += 1) {
      const [r, g, b] = getPixel(frame, x, y);
      let colour: string = theme.pixel.offLed;
      if (r + g + b > 0) colour = `rgb(${r},${g},${b})`;
      else if (onion) {
        const [or, og, ob] = getPixel(onion, x, y);
        if (or + og + ob > 0) colour = `rgba(${or},${og},${ob},0.28)`;
      }
      ctx.fillStyle = colour;
      ctx.fillRect(x * pitch + gap, y * pitch + gap, pitch - 2 * gap, pitch - 2 * gap);
    }
  }
  if (cursor) {
    ctx.strokeStyle = theme.pixel.cursor;
    ctx.lineWidth = 2;
    ctx.strokeRect(cursor[0] * pitch, cursor[1] * pitch, pitch, pitch);
  }
}

export const DrawBody: FC<{ initial: DrawingDraft; onSent: (id: string) => void }> = ({ initial, onSent }) => {
  const { t } = useI18n();
  const { close, leave, markDirty } = useEditorControls();
  const [saveFailed, setSaveFailed] = useState(false);
  const [frames, setFrames] = useState<Uint8Array[]>(() => initial.frames.length ? initial.frames.map((f) => new Uint8Array(f)) : [blankFrame()]);
  const [index, setIndex] = useState(0);
  const [colour, setColour] = useState<Rgb>(DRAW_PALETTE[9]);
  const [tool, setTool] = useState<Tool>("pencil");
  const [mirror, setMirror] = useState(false);
  const [onion, setOnion] = useState(true);
  const [fps, setFps] = useState(initial.fps || 8);
  // Left empty rather than a translated "Untitled", which would stick after a language change.
  const [name, setName] = useState(initial.name || "");
  const [cursor, setCursor] = useState<[number, number]>([32, 27]);
  const [busy, setBusy] = useState(false);
  const [canvasFocused, setCanvasFocused] = useState(false);
  // While painting the canvas owns the d-pad; B or pushing past an edge hands it back to the editor.
  const [painting, setPainting] = useState(false);
  const [, redraw] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawingId = useRef(initial.id);
  const dragging = useRef(false);
  const history = useRef<{ frames: Uint8Array[]; index: number }[]>([]);

  const frame = frames[index];
  // Cheap enough to run every render, and the canvas may have just been resized to fit.
  const repaint = () => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (element && ctx) drawCanvas(ctx, frame, onion && index > 0 ? frames[index - 1] : null, painting ? cursor : null, element.width / PANEL_W);
  };
  useEffect(repaint);

  const dirty = () => {
    markDirty();
    setSaveFailed(false);
  };
  // Fill and clearing the only frame wipe a lot at once: every change can be stepped back.
  const remember = () => {
    history.current = [...history.current.slice(1 - UNDO_STEPS), { frames: frames.map((f) => new Uint8Array(f)), index }];
  };
  const undo = () => {
    const last = history.current.pop();
    if (!last) return;
    dirty();
    setFrames(last.frames);
    setIndex(last.index);
    redraw((n) => n + 1);
  };
  const apply = (x: number, y: number, chosen: Tool = tool, stroke = true) => {
    if (stroke) remember();
    dirty();
    if (chosen === "fill") fill(frame, x, y, colour);
    else paint(frame, x, y, chosen === "eraser" ? [0, 0, 0] : colour, mirror);
    redraw((n) => n + 1);
  };

  const onDirection = (event: GamepadEvent) => {
    const move = DIRECTIONS[event.detail.button];
    if (!move) return;
    event.preventDefault();
    event.stopPropagation();
    const next: [number, number] = [cursor[0] + move[0], cursor[1] + move[1]];
    if (next[0] < 0 || next[0] >= PANEL_W || next[1] < 0 || next[1] >= PANEL_H) setPainting(false);
    else setCursor(next);
  };
  const stopPainting = (event: GamepadEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setPainting(false);
  };

  const onButton = (event: GamepadEvent) => {
    const button = event.detail.button;
    if (button === GamepadButton.TRIGGER_LEFT) {
      event.preventDefault();
      event.stopPropagation();
      undo();
      return;
    }
    if (button !== GamepadButton.BUMPER_LEFT && button !== GamepadButton.BUMPER_RIGHT) return;
    event.preventDefault();
    event.stopPropagation();
    const at = DRAW_PALETTE.findIndex((c) => sameColour(c, colour));
    const delta = button === GamepadButton.BUMPER_LEFT ? -1 : 1;
    setColour(DRAW_PALETTE[(at + delta + DRAW_PALETTE.length) % DRAW_PALETTE.length]);
  };

  const cellFrom = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.floor((e.clientX - rect.left) / (rect.width / PANEL_W));
    const y = Math.floor((e.clientY - rect.top) / (rect.height / PANEL_H));
    return [Math.max(0, Math.min(PANEL_W - 1, x)), Math.max(0, Math.min(PANEL_H - 1, y))];
  };

  const addFrame = (copy: boolean) => {
    if (frames.length >= MAX_FRAMES) return;
    remember();
    dirty();
    const next = copy ? new Uint8Array(frame) : blankFrame();
    setFrames([...frames.slice(0, index + 1), next, ...frames.slice(index + 1)]);
    setIndex(index + 1);
  };
  const removeFrame = () => {
    remember();
    dirty();
    if (frames.length === 1) {
      frame.fill(0);
      redraw((n) => n + 1);
      return;
    }
    setFrames(frames.filter((_, i) => i !== index));
    setIndex(Math.max(0, index - 1));
  };

  const send = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await saveAccessoryDrawing({ id: drawingId.current, name: name.trim(), frames: frames.map(encodeFrame), fps });
      if (result?.ok && result.id) {
        drawingId.current = result.id;
        onSent(result.id);
        close();
      } else {
        setSaveFailed(true);
      }
    } catch {
      setSaveFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const pad = {
    direction: useLive(onDirection),
    bumper: useLive(onButton),
    stop: useLive(stopPainting),
    ok: useLive(() => { if (painting) apply(cursor[0], cursor[1]); else setPainting(true); }),
    erase: useLive(() => { if (painting) apply(cursor[0], cursor[1], "eraser"); }),
    fill: useLive(() => { if (painting) apply(cursor[0], cursor[1], "fill"); }),
    send: useLive(() => void send()),
  };

  const stage = (pitch: number) => (
    // Steam hands every d-pad press to a Focusable that has a direction handler, so the canvas
    // only takes them while painting.
    <Focusable onGamepadDirection={painting ? pad.direction : undefined} onButtonDown={painting ? pad.bumper : undefined}
      onOKButton={pad.ok} onSecondaryButton={pad.erase} onOptionsButton={pad.fill}
      onCancelButton={painting ? pad.stop : undefined}
      onOKActionDescription={painting ? t(`accessories.draw.tool.${tool}`) : t("accessories.draw.start")}
      onCancelActionDescription={painting ? t("accessories.draw.stop") : undefined}
      onSecondaryActionDescription={painting ? t("accessories.draw.tool.eraser") : undefined}
      onOptionsActionDescription={painting ? t("accessories.draw.tool.fill") : undefined}
      onMenuButton={pad.send} onMenuActionDescription={t("accessories.draw.send")}
      onGamepadFocus={() => { setCanvasFocused(true); setPainting(true); }}
      onGamepadBlur={() => { setCanvasFocused(false); setPainting(false); }} noFocusRing
      style={{ borderRadius: theme.radius.md, overflow: "hidden", flex: "0 0 auto", transition: "box-shadow 120ms ease",
        boxShadow: `0 0 0 ${canvasFocused ? 3 : 1}px ${painting ? theme.color.accent : canvasFocused ? theme.color.textPrimary : theme.color.outline}, ${theme.pixel.shadow}` }}>
      <canvas ref={canvas} width={PANEL_W * pitch} height={PANEL_H * pitch} style={{ display: "block", touchAction: "none" }}
        onPointerDown={(e) => { dragging.current = true; const [x, y] = cellFrom(e); setCursor([x, y]); apply(x, y); }}
        onPointerMove={(e) => { if (!dragging.current || tool === "fill") return; const [x, y] = cellFrom(e); setCursor([x, y]); apply(x, y, tool, false); }}
        onPointerUp={() => { dragging.current = false; }} onPointerLeave={() => { dragging.current = false; }} />
    </Focusable>
  );

  const timeline = (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: theme.space.xs, justifyContent: "center" }}>
        <IconButton label={t("accessories.draw.frame.prev")} onPress={() => setIndex(Math.max(0, index - 1))} disabled={index === 0}><LuChevronLeft /></IconButton>
        <span style={{ minWidth: 130, textAlign: "center", fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          {t("accessories.draw.frame.of", { n: index + 1, total: frames.length })}
        </span>
        <IconButton label={t("accessories.draw.frame.next")} onPress={() => setIndex(Math.min(frames.length - 1, index + 1))} disabled={index === frames.length - 1}><LuChevronRight /></IconButton>
        <span style={{ width: theme.space.md }} />
        <IconButton label={t("accessories.draw.frame.add")} onPress={() => addFrame(false)} disabled={frames.length >= MAX_FRAMES}><LuPlus /></IconButton>
        <IconButton label={t("accessories.draw.frame.copy")} onPress={() => addFrame(true)} disabled={frames.length >= MAX_FRAMES}><LuCopy /></IconButton>
        <IconButton label={t("accessories.draw.frame.delete")} onPress={removeFrame}><LuTrash2 /></IconButton>
        <IconButton label={t("accessories.draw.undo")} onPress={undo} disabled={history.current.length === 0}><LuUndo2 /></IconButton>
      </Focusable>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textAlign: "center" }}>{t("accessories.draw.hint")}</span>
    </div>
  );

  const swatchRows: Rgb[][] = [];
  for (let i = 0; i < DRAW_PALETTE.length; i += SWATCHES_PER_ROW) swatchRows.push(DRAW_PALETTE.slice(i, i + SWATCHES_PER_ROW));

  const inspector = (
    <>
      <InspectorGroup label={t("accessories.editor.name")}>
        <TextField value={name} onChange={(e) => { dirty(); setName(e.target.value.slice(0, 40)); }} />
      </InspectorGroup>
      <InspectorGroup label={t("accessories.editor.tool")}>
        <ChipRow>
          <Chip active={tool === "pencil"} label={t("accessories.draw.tool.pencil")} icon={<LuPencil />} onPick={() => setTool("pencil")} />
          <Chip active={tool === "eraser"} label={t("accessories.draw.tool.eraser")} icon={<LuEraser />} onPick={() => setTool("eraser")} />
          <Chip active={tool === "fill"} label={t("accessories.draw.tool.fill")} icon={<LuPaintBucket />} onPick={() => setTool("fill")} />
        </ChipRow>
        <ChipRow>
          <Chip active={mirror} label={t("accessories.draw.mirror")} icon={<LuFlipHorizontal2 />} onPick={() => setMirror(!mirror)} />
          <Chip active={onion} label={t("accessories.draw.onion")} icon={<LuLayers />} onPick={() => setOnion(!onion)} />
        </ChipRow>
      </InspectorGroup>
      <InspectorGroup label={t("accessories.editor.colour")}>
        <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          {swatchRows.map((row) => (
            <Focusable key={row[0].join(",")} flow-children="row" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_X} style={{ display: "flex", gap: theme.space.xs }}>
              {row.map((rgb) => {
                const selected = sameColour(rgb, colour);
                return (
                  <Focusable key={rgb.join(",")} onActivate={() => setColour(rgb)} onClick={() => setColour(rgb)}
                    aria-label={`rgb(${rgb.join(",")})`}
                    style={{ flex: 1, height: 28, borderRadius: theme.radius.sm, background: `rgb(${rgb.join(",")})`,
                      boxShadow: selected ? `0 0 0 2px ${theme.color.surface}, 0 0 0 4px ${theme.color.accent}` : `inset 0 0 0 1px ${theme.color.outline}` }}>
                    <span />
                  </Focusable>
                );
              })}
            </Focusable>
          ))}
        </Focusable>
      </InspectorGroup>
      {frames.length > 1 && (
        <InspectorGroup label={t("accessories.editor.speed")}>
          <ChipRow>
            {SPEEDS.map((value) => (
              <Chip key={value} active={fps === value} label={t(`accessories.draw.speed.${value}`)} onPick={() => { dirty(); setFps(value); }} />
            ))}
          </ChipRow>
        </InspectorGroup>
      )}
    </>
  );

  return (
    <EditorShell icon={<LuPencil size={22} />} title={t("accessories.editor.draw")} stage={stage} stageFooter={timeline}
      inspector={inspector} primaryLabel={t("accessories.draw.send")} primaryIcon={<LuSend />} primaryBusy={busy}
      onPrimary={() => void send()} onClose={leave} notice={saveFailed ? t("accessories.draw.saveFailed") : null} />
  );
};
