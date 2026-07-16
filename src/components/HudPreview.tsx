import { FC } from "react";

import { HudModel, SPACER_LINES, previewRows } from "../mangohud/model";

// The miniature shrinks the real px size to fit the small frame while staying
// proportional, so a bigger font_size visibly grows the preview.
const PREVIEW_SCALE = 0.5;
const clampPx = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/**
 * Faithful preview of the in-game overlay. Mirrors how MangoHud actually draws:
 * consecutive GPU/CPU metrics collapse into ONE row (category label tinted by its
 * colour, then a white value per column); other metrics/custom text are single
 * lines; separators draw a plain-ASCII divider (MangoHud's font has no box glyphs).
 * Honours corner, vertical/horizontal layout, opacity/rounding, size, labels,
 * small-font. Tall HUDs scroll inside the frame so every row is visible (no clipping).
 */
export const HudPreview: FC<{ model: HudModel }> = ({ model }) => {
  const rows = previewRows(model);
  const top = model.position.startsWith("top");
  const left = model.position.endsWith("left");
  const horizontal = model.layout === "horizontal";
  // font_scale multiplies font_size in MangoHud; reflect both. Secondary text uses
  // font_size_text (unless no_small_font pins it to the main size).
  const base = clampPx(Math.round(model.fontSize * model.fontScale * PREVIEW_SCALE), 8, 22);
  const smallBase = model.noSmallFont
    ? base
    : clampPx(Math.round(model.fontSizeText * model.fontScale * PREVIEW_SCALE), 6, base);
  const lineH = Math.round(base * 1.35);
  // In vertical layout the divider is a custom_text row → it shares text_color;
  // only the horizontal native separator honours separatorColor.
  const sepColor = horizontal && model.separatorColor ? `#${model.separatorColor}` : `#${model.colors.text}`;
  const [br, bg, bb] = [model.colors.background.slice(0, 2), model.colors.background.slice(2, 4), model.colors.background.slice(4, 6)].map((h) => parseInt(h, 16));
  const boxBg = `rgba(${br || 0},${bg || 0},${bb || 0},${model.background.alpha})`;
  return (
    <div
      style={{
        position: "relative",
        height: 168,
        borderRadius: 10,
        overflow: "hidden",
        background: "linear-gradient(135deg, #1a2740, #101b2e)",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: top ? 8 : undefined,
          bottom: top ? undefined : 8,
          left: left ? 8 : undefined,
          right: left ? undefined : 8,
          display: "flex",
          flexDirection: horizontal ? "row" : "column",
          flexWrap: horizontal ? "wrap" : "nowrap",
          alignItems: horizontal ? "center" : left ? "flex-start" : "flex-end",
          gap: horizontal ? 10 : 1,
          textAlign: left ? "left" : "right",
          padding: "6px 8px",
          borderRadius: model.background.roundCorners ? 6 : 0,
          background: boxBg,
          fontFamily: "monospace",
          fontSize: base,
          lineHeight: 1.35,
          maxWidth: "92%",
          maxHeight: 152,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {rows.length === 0 ? (
          <div style={{ color: "rgba(255,255,255,0.4)" }}>—</div>
        ) : (
          rows.map((r) => {
            if (r.kind === "spacer") {
              return <div key={r.key} style={{ height: SPACER_LINES[r.size] * lineH, flexShrink: 0 }} />;
            }
            if (r.kind === "separator") {
              return horizontal ? (
                <div key={r.key} style={{ width: 1, alignSelf: "stretch", background: sepColor }} />
              ) : (
                <div key={r.key} style={{ color: sepColor, whiteSpace: "nowrap", overflow: "hidden" }}>
                  {"-".repeat(14)}
                </div>
              );
            }
            if (r.kind === "group") {
              return (
                <div key={r.key} style={{ display: "flex", gap: 6, whiteSpace: "nowrap" }}>
                  <span style={{ color: r.labelColor, fontWeight: 600 }}>{r.label}</span>
                  {r.cells.map((c, i) => (
                    <span key={i} style={{ color: r.valueColor }}>{c}</span>
                  ))}
                </div>
              );
            }
            return (
              <div
                key={r.key}
                style={{
                  display: "flex",
                  gap: 5,
                  whiteSpace: "nowrap",
                  fontSize: r.small ? smallBase : base,
                }}
              >
                {r.label && <span style={{ color: r.labelColor, fontWeight: 600 }}>{r.label}</span>}
                <span style={{ color: r.valueColor }}>{r.value}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
