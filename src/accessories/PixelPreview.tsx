import { CSSProperties, FC, useEffect, useRef } from "react";
import { LuCar, LuHexagon, LuSparkles, LuTriangle } from "react-icons/lu";

import { DecodedFrames, frameAt, PANEL_H, PANEL_W } from "./pixelFrames";

const OFF_LED = "rgb(28,24,26)";
const FACE = "#0a090b";
const FIRMWARE_ICONS = [LuTriangle, LuHexagon, LuSparkles, LuCar];
const FIRMWARE_TINTS = ["#ff5fa2,#7a5cff", "#4fd1ff,#7a5cff", "#ffb347,#ff4f6d", "#ffcf70,#ff7a3d"];

function paint(ctx: CanvasRenderingContext2D, decoded: DecodedFrames, index: number, pitch: number, glow: boolean) {
  const frame = decoded.frames[index];
  ctx.fillStyle = FACE;
  ctx.fillRect(0, 0, PANEL_W * pitch, PANEL_H * pitch);
  const dot = Math.max(1, pitch * 0.78);
  const inset = (pitch - dot) / 2;
  for (let y = 0; y < PANEL_H; y += 1) {
    for (let x = 0; x < PANEL_W; x += 1) {
      const rgb = decoded.palette[frame[y * PANEL_W + x]] ?? [0, 0, 0];
      const lit = rgb[0] + rgb[1] + rgb[2] > 0;
      if (!lit && glow) continue;
      ctx.fillStyle = lit ? `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` : OFF_LED;
      ctx.fillRect(x * pitch + inset, y * pitch + inset, dot, dot);
    }
  }
}

/** The panel as it looks lit: LED dots, a soft bloom, and the real frame timing. */
export const PixelPreview: FC<{
  decoded: DecodedFrames | null;
  pitch: number;
  animate: boolean;
  label?: string;
  style?: CSSProperties;
}> = ({ decoded, pitch, animate, label, style }) => {
  const base = useRef<HTMLCanvasElement>(null);
  const bloom = useRef<HTMLCanvasElement>(null);
  const width = Math.round(PANEL_W * pitch);
  const height = Math.round(PANEL_H * pitch);

  useEffect(() => {
    if (!decoded || !decoded.frames.length) return undefined;
    const draw = (index: number) => {
      const a = base.current?.getContext("2d");
      const b = bloom.current?.getContext("2d");
      if (a) paint(a, decoded, index, pitch, false);
      if (b) paint(b, decoded, index, pitch, true);
    };
    const started = performance.now();
    let timer = 0;
    const step = () => {
      const elapsed = performance.now() - started;
      const index = frameAt(decoded.delaysMs, elapsed);
      draw(index);
      if (!animate || decoded.frames.length < 2) return;
      let until = 0;
      for (let i = 0; i <= index; i += 1) until += decoded.delaysMs[i];
      const total = decoded.delaysMs.reduce((s, d) => s + d, 0);
      timer = window.setTimeout(step, Math.max(16, until - (elapsed % total)));
    };
    step();
    return () => window.clearTimeout(timer);
  }, [decoded, pitch, animate]);

  const frameStyle: CSSProperties = {
    position: "relative",
    width,
    height,
    borderRadius: Math.max(6, pitch * 2),
    overflow: "hidden",
    background: FACE,
    boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06), 0 10px 30px rgba(0,0,0,0.45)",
    flex: "0 0 auto",
    ...style,
  };

  if (decoded && decoded.firmwareAnimation !== null) {
    const Icon = FIRMWARE_ICONS[decoded.firmwareAnimation] ?? LuSparkles;
    const tint = FIRMWARE_TINTS[decoded.firmwareAnimation] ?? FIRMWARE_TINTS[2];
    const [from, to] = tint.split(",");
    return (
      <div aria-label={label} style={{ ...frameStyle, display: "flex", alignItems: "center", justifyContent: "center",
        background: `radial-gradient(circle at 35% 30%, ${from}33, transparent 55%), radial-gradient(circle at 70% 75%, ${to}33, transparent 55%), ${FACE}` }}>
        <Icon size={Math.round(height * 0.42)} color={from} style={{ filter: `drop-shadow(0 0 ${pitch * 3}px ${from})` }} />
      </div>
    );
  }

  return (
    <div aria-label={label} style={frameStyle}>
      <canvas ref={base} width={width} height={height} style={{ position: "absolute", inset: 0 }} />
      <canvas ref={bloom} width={width} height={height}
        style={{ position: "absolute", inset: 0, filter: `blur(${Math.max(1.5, pitch * 0.9)}px)`, opacity: 0.55, mixBlendMode: "screen" }} />
      {!decoded && <div style={{ position: "absolute", inset: 0, background: `linear-gradient(110deg, transparent 30%, rgba(255,255,255,0.04) 50%, transparent 70%)` }} />}
      <div style={{ position: "absolute", inset: 0, borderRadius: "inherit", boxShadow: `inset 0 0 ${pitch * 6}px rgba(0,0,0,0.55)`, pointerEvents: "none" }} />
    </div>
  );
};
