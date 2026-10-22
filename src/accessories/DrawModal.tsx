import { DialogButton, Focusable, GamepadButton, GamepadEvent, ModalRoot, TextField } from "@decky/ui";
import { FC, useCallback, useEffect, useRef, useState } from "react";
import { LuCopy, LuEraser, LuFlipHorizontal2, LuLayers, LuPaintBucket, LuPencil, LuPlus, LuSend, LuTrash2 } from "react-icons/lu";

import { saveAccessoryDrawing } from "../api";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";
import { confirmDestructive } from "./SafeConfirm";
import { blankFrame, DRAW_PALETTE, encodeFrame, fill, getPixel, paint, Rgb } from "./drawing";
import { PANEL_H, PANEL_W } from "./pixelFrames";

const PITCH = 7;
const MAX_FRAMES = 48;
const SPEEDS = [4, 8, 12];
type Tool = "pencil" | "eraser" | "fill";

export interface DrawingDraft {
  id?: string;
  name: string;
  frames: Uint8Array[];
  fps: number;
}

function drawCanvas(ctx: CanvasRenderingContext2D, frame: Uint8Array, onion: Uint8Array | null, cursor: [number, number] | null) {
  ctx.fillStyle = "#0a090b";
  ctx.fillRect(0, 0, PANEL_W * PITCH, PANEL_H * PITCH);
  for (let y = 0; y < PANEL_H; y += 1) {
    for (let x = 0; x < PANEL_W; x += 1) {
      const [r, g, b] = getPixel(frame, x, y);
      let colour = "rgb(30,26,30)";
      if (r + g + b > 0) colour = `rgb(${r},${g},${b})`;
      else if (onion) {
        const [or, og, ob] = getPixel(onion, x, y);
        if (or + og + ob > 0) colour = `rgba(${or},${og},${ob},0.28)`;
      }
      ctx.fillStyle = colour;
      ctx.fillRect(x * PITCH + 1, y * PITCH + 1, PITCH - 2, PITCH - 2);
    }
  }
  if (cursor) {
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(cursor[0] * PITCH, cursor[1] * PITCH, PITCH, PITCH);
  }
}

const ToolButton: FC<{ active: boolean; label: string; onPick: () => void; children: React.ReactNode }> = ({ active, label, onPick, children }) => (
  <DialogButton onClick={onPick} aria-label={label}
    style={{ minWidth: 0, flex: 1, padding: "8px 0", display: "flex", justifyContent: "center",
      background: active ? theme.color.accent : undefined, color: active ? theme.color.onAccent : undefined }}>
    {children}
  </DialogButton>
);

const DrawBody: FC<{ onDirty?: () => void; initial: DrawingDraft; onSent: (id: string) => void; closeModal?: () => void }> = ({ initial, onSent, closeModal, onDirty }) => {
  const { t } = useI18n();
  const [saveFailed, setSaveFailed] = useState(false);
  const [frames, setFrames] = useState<Uint8Array[]>(() => initial.frames.length ? initial.frames.map((f) => new Uint8Array(f)) : [blankFrame()]);
  const [index, setIndex] = useState(0);
  const [colour, setColour] = useState<Rgb>(DRAW_PALETTE[9]);
  const [tool, setTool] = useState<Tool>("pencil");
  const [mirror, setMirror] = useState(false);
  const [onion, setOnion] = useState(true);
  const [fps, setFps] = useState(initial.fps || 8);
  const [name, setName] = useState(initial.name || t("accessories.draw.untitled"));
  const [cursor, setCursor] = useState<[number, number]>([32, 27]);
  const [busy, setBusy] = useState(false);
  const [, redraw] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawingId = useRef(initial.id);
  const dragging = useRef(false);

  const frame = frames[index];
  const repaint = useCallback(() => {
    const ctx = canvas.current?.getContext("2d");
    if (ctx) drawCanvas(ctx, frame, onion && index > 0 ? frames[index - 1] : null, cursor);
  }, [frame, frames, index, onion, cursor]);
  useEffect(repaint, [repaint]);

  const apply = (x: number, y: number, chosen: Tool = tool) => {
    onDirty?.();
    if (chosen === "fill") fill(frame, x, y, colour);
    else paint(frame, x, y, chosen === "eraser" ? [0, 0, 0] : colour, mirror);
    redraw((n) => n + 1);
    repaint();
  };

  const onDirection = (event: GamepadEvent) => {
    const step: Record<number, [number, number]> = {
      [GamepadButton.DIR_LEFT]: [-1, 0], [GamepadButton.DIR_RIGHT]: [1, 0],
      [GamepadButton.DIR_UP]: [0, -1], [GamepadButton.DIR_DOWN]: [0, 1],
    };
    const move = step[event.detail.button];
    if (!move) return;
    const next: [number, number] = [cursor[0] + move[0], cursor[1] + move[1]];
    if (next[0] < 0 || next[0] >= PANEL_W) return;
    if (next[1] < 0 || next[1] >= PANEL_H) return;
    event.preventDefault();
    event.stopPropagation();
    setCursor(next);
  };

  const onButton = (event: GamepadEvent) => {
    const button = event.detail.button;
    if (button === GamepadButton.BUMPER_LEFT || button === GamepadButton.BUMPER_RIGHT) {
      const at = DRAW_PALETTE.findIndex((c) => c.every((v, k) => v === colour[k]));
      const delta = button === GamepadButton.BUMPER_LEFT ? -1 : 1;
      setColour(DRAW_PALETTE[(at + delta + DRAW_PALETTE.length) % DRAW_PALETTE.length]);
      event.preventDefault();
    }
  };

  const cellFrom = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [Math.floor((e.clientX - rect.left) / (rect.width / PANEL_W)), Math.floor((e.clientY - rect.top) / (rect.height / PANEL_H))];
  };

  const addFrame = (copy: boolean) => {
    if (frames.length >= MAX_FRAMES) return;
    onDirty?.();
    const next = copy ? new Uint8Array(frame) : blankFrame();
    const list = [...frames.slice(0, index + 1), next, ...frames.slice(index + 1)];
    setFrames(list);
    setIndex(index + 1);
  };
  const removeFrame = () => {
    onDirty?.();
    if (frames.length === 1) {
      frame.fill(0);
      redraw((n) => n + 1);
      repaint();
      return;
    }
    const list = frames.filter((_, i) => i !== index);
    setFrames(list);
    setIndex(Math.max(0, index - 1));
  };

  const send = async () => {
    setBusy(true);
    try {
      const result = await saveAccessoryDrawing({ id: drawingId.current, name, frames: frames.map(encodeFrame), fps });
      if (result?.ok && result.id) {
        drawingId.current = result.id;
        onSent(result.id);
        closeModal?.();
      } else {
        setSaveFailed(true);
      }
    } catch {
      setSaveFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", gap: theme.space.lg, padding: theme.space.sm }}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <Focusable onGamepadDirection={onDirection} onButtonDown={onButton} onOKButton={() => apply(cursor[0], cursor[1])}
          onSecondaryButton={() => apply(cursor[0], cursor[1], "eraser")} onOptionsButton={() => apply(cursor[0], cursor[1], "fill")}
          onOKActionDescription={t(`accessories.draw.tool.${tool}`)} onSecondaryActionDescription={t("accessories.draw.tool.eraser")}
          onOptionsActionDescription={t("accessories.draw.tool.fill")}
          style={{ borderRadius: theme.radius.md, overflow: "hidden", boxShadow: `0 0 0 1px ${theme.color.outline}, 0 12px 40px rgba(0,0,0,0.5)` }}>
          <canvas ref={canvas} width={PANEL_W * PITCH} height={PANEL_H * PITCH} style={{ display: "block", touchAction: "none" }}
            onPointerDown={(e) => { dragging.current = true; const [x, y] = cellFrom(e); setCursor([x, y]); apply(x, y); }}
            onPointerMove={(e) => { if (!dragging.current || tool === "fill") return; const [x, y] = cellFrom(e); setCursor([x, y]); apply(x, y); }}
            onPointerUp={() => { dragging.current = false; }} onPointerLeave={() => { dragging.current = false; }} />
        </Focusable>
        <Focusable flow-children="row" style={{ display: "flex", gap: 6, alignItems: "center", overflowX: "auto", maxWidth: PANEL_W * PITCH }}>
          {frames.map((_, i) => (
            <DialogButton key={i} onClick={() => setIndex(i)}
              style={{ minWidth: 34, width: 34, padding: "6px 0", background: i === index ? theme.color.accent : undefined,
                color: i === index ? theme.color.onAccent : undefined }}>
              {i + 1}
            </DialogButton>
          ))}
          <DialogButton onClick={() => addFrame(false)} aria-label={t("accessories.draw.frame.add")} style={{ minWidth: 34, width: 34, padding: "6px 0" }}><LuPlus /></DialogButton>
          <DialogButton onClick={() => addFrame(true)} aria-label={t("accessories.draw.frame.copy")} style={{ minWidth: 34, width: 34, padding: "6px 0" }}><LuCopy /></DialogButton>
          <DialogButton onClick={removeFrame} aria-label={t("accessories.draw.frame.delete")} style={{ minWidth: 34, width: 34, padding: "6px 0" }}><LuTrash2 /></DialogButton>
        </Focusable>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, width: 220 }}>
        <TextField value={name} onChange={(e) => { onDirty?.(); setName(e.target.value.slice(0, 40)); }} />
        <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
          {DRAW_PALETTE.map((rgb) => {
            const selected = rgb.every((v, k) => v === colour[k]);
            return (
              <Focusable key={rgb.join(",")} onActivate={() => setColour(rgb)} onClick={() => setColour(rgb)}
                style={{ height: 30, borderRadius: 8, background: `rgb(${rgb.join(",")})`,
                  boxShadow: selected ? `0 0 0 2px ${theme.color.surface}, 0 0 0 4px ${theme.color.accent}` : `inset 0 0 0 1px rgba(255,255,255,0.12)` }}>
                <span />
              </Focusable>
            );
          })}
        </Focusable>
        <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
          <ToolButton active={tool === "pencil"} label={t("accessories.draw.tool.pencil")} onPick={() => setTool("pencil")}><LuPencil /></ToolButton>
          <ToolButton active={tool === "eraser"} label={t("accessories.draw.tool.eraser")} onPick={() => setTool("eraser")}><LuEraser /></ToolButton>
          <ToolButton active={tool === "fill"} label={t("accessories.draw.tool.fill")} onPick={() => setTool("fill")}><LuPaintBucket /></ToolButton>
        </Focusable>
        <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
          <ToolButton active={mirror} label={t("accessories.draw.mirror")} onPick={() => setMirror(!mirror)}><LuFlipHorizontal2 /></ToolButton>
          <ToolButton active={onion} label={t("accessories.draw.onion")} onPick={() => setOnion(!onion)}><LuLayers /></ToolButton>
        </Focusable>
        {frames.length > 1 && (
          <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
            {SPEEDS.map((value) => (
              <ToolButton key={value} active={fps === value} label={`${value} fps`} onPick={() => setFps(value)}>
                <span style={{ fontSize: 12, fontWeight: 700 }}>{t(`accessories.draw.speed.${value}`)}</span>
              </ToolButton>
            ))}
          </Focusable>
        )}
        <div style={{ flex: 1 }} />
        <DialogButton onClick={() => void send()} disabled={busy}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700 }}>
          <LuSend /> {t("accessories.draw.send")}
        </DialogButton>
        {saveFailed && <span style={{ fontSize: 11, color: theme.color.warn }}>{t("accessories.draw.saveFailed")}</span>}
        <span style={{ fontSize: 11, color: theme.color.textMuted, lineHeight: 1.4 }}>{t("accessories.draw.hint")}</span>
      </div>
    </div>
  );
};

const DrawModal: FC<{ initial: DrawingDraft; onSent: (id: string) => void; closeModal?: () => void }> = ({ initial, onSent, closeModal }) => {
  const { t } = useI18n();
  const dirty = useRef(false);
  const leave = () => {
    if (!dirty.current) return closeModal?.();
    confirmDestructive({ title: t("accessories.draw.discardTitle"), desc: t("accessories.draw.discardDesc"),
      confirmLabel: t("accessories.draw.discard"), cancelLabel: t("accessories.draw.keepEditing"), onConfirm: () => closeModal?.() });
  };
  return (
    <ModalRoot onCancel={leave} onEscKeypress={leave}>
      <DrawBody initial={initial} onSent={onSent} closeModal={closeModal} onDirty={() => { dirty.current = true; }} />
    </ModalRoot>
  );
};

export function openDrawModal(initial: DrawingDraft, onSent: (id: string) => void): void {
  showModal(<DrawModal initial={initial} onSent={onSent} />, window);
}
