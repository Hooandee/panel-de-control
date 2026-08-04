import { FC } from "react";

import { useI18n } from "../i18n";
import {
  HudModel,
  MetricId,
  SPACER_LINES,
  previewRows,
  previewWouldClip,
} from "../mangohud/model";

// The miniature shrinks the real px size to fit the small frame while staying
// proportional, so a bigger font_size visibly grows the preview.
const PREVIEW_SCALE = 0.5;
const clampPx = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const VALUE_UNIT = /^(.+?)(%|°[CF]|ms|MHz|GHz|kHz|Hz|rpm|[WVG])$/;

function valueParts(value: string): { main: string; unit: string } {
  const match = value.match(VALUE_UNIT);
  return match ? { main: match[1], unit: match[2] } : { main: value, unit: "" };
}

/**
 * Faithful preview of the in-game overlay. Mirrors how MangoHud actually draws:
 * consecutive GPU/CPU metrics collapse into ONE row (category label tinted by its
 * colour, then a white value per column); other metrics/custom text are single
 * lines; separators draw a plain-ASCII divider (MangoHud's font has no box glyphs).
 * Honours corner, vertical/horizontal layout, opacity/rounding, size, labels,
 * small-font. Tall HUDs clip like the real viewport and surface that limitation.
 */
export const HudPreview: FC<{
  model: HudModel;
  values?: Partial<Record<MetricId, string>>;
}> = ({ model, values }) => {
  const { t } = useI18n();
  const rows = previewRows(model, values);
  const clips = previewWouldClip(model);
  const top = model.position.startsWith("top");
  const left = model.position.endsWith("left");
  const horizontal = model.layout === "horizontal";
  const base = clampPx(Math.round(model.fontSize * model.fontScale * PREVIEW_SCALE), 8, 22);
  const secondaryBase = model.noSmallFont
    ? base
    : clampPx(Math.round(model.fontSizeSecondary * model.fontScale * PREVIEW_SCALE), 6, 32);
  const textBase = model.noSmallFont
    ? base
    : clampPx(Math.round(model.fontSizeText * model.fontScale * PREVIEW_SCALE), 6, 32);
  const lineH = Math.round(base * 1.35);
  const sepColor = `#${model.colors.text}`;
  const [br, bg, bb] = [model.colors.background.slice(0, 2), model.colors.background.slice(2, 4), model.colors.background.slice(4, 6)].map((h) => parseInt(h, 16));
  const boxBg = `rgba(${br || 0},${bg || 0},${bb || 0},${model.background.alpha})`;
  const pad = model.noMargin ? 0 : model.compact ? 4 : 6;
  const rowGap = clampPx(Math.round(1 + model.cellpaddingY * base), 0, 9);
  const outlineWidth = model.textOutline
    ? Math.max(0.25, model.textOutlineThickness * PREVIEW_SCALE)
    : 0;
  const textAlpha = Math.round(Math.max(0, Math.min(1, model.alpha)) * 255)
    .toString(16)
    .padStart(2, "0");
  const textColor = (hex: string) => `${hex}${textAlpha}`;
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: 5, minWidth: 0 }}
    >
    <div
      data-testid="hud-preview-frame"
      style={{
        position: "relative",
        height: 168,
        borderRadius: 10,
        overflow: "hidden",
        background: "linear-gradient(135deg, #1a2740, #101b2e)",
      }}
    >
      <div
        data-testid="hud-preview-overlay"
        style={{
          position: "absolute",
          top: top ? 8 : undefined,
          bottom: top ? undefined : 8,
          left: left ? 8 : undefined,
          right: left ? undefined : 8,
          transform: `translate(${model.offsetX * PREVIEW_SCALE}px, ${model.offsetY * PREVIEW_SCALE}px)`,
          display: "flex",
          flexDirection: horizontal ? "row" : "column",
          flexWrap: horizontal ? "wrap" : "nowrap",
          alignItems: horizontal ? "center" : left ? "flex-start" : "flex-end",
          gap: horizontal ? (model.compact ? 5 : 10) : rowGap,
          textAlign: left ? "left" : "right",
          padding: `${pad}px ${pad + (model.noMargin ? 0 : 2)}px`,
          borderRadius: model.background.roundCorners ? 6 : 0,
          background: boxBg,
          fontFamily: "monospace",
          fontSize: base,
          lineHeight: 1.35,
          maxWidth: "92%",
          maxHeight: 152,
          overflow: "hidden",
          WebkitTextStroke: outlineWidth
            ? `${outlineWidth}px #${model.colors.outline}${textAlpha}`
            : undefined,
        }}
      >
        {rows.length === 0 ? (
          <div style={{ color: "rgba(255,255,255,0.4)" }}>—</div>
        ) : rows.map((r) => {
            if (r.kind === "spacer") {
              return <div key={r.key} style={{ height: SPACER_LINES[r.size] * lineH, flexShrink: 0 }} />;
            }
            if (r.kind === "separator") {
              return (
                <div key={r.key} style={{ color: textColor(sepColor), whiteSpace: "nowrap", overflow: "hidden" }}>
                  {"-".repeat(14)}
                </div>
              );
            }
            if (r.kind === "group") {
              return (
                <div key={r.key} style={{ display: "flex", gap: 6, whiteSpace: "nowrap" }}>
                  <span style={{ color: textColor(r.labelColor), fontWeight: 600 }}>{r.label}</span>
                  {r.cells.map((cell, i) => {
                    const { main, unit } = valueParts(cell);
                    return (
                      <span key={i} style={{ color: textColor(r.valueColor) }}>
                        <span>{main}</span>
                        {unit && (
                          <span data-hud-value-unit style={{ fontSize: secondaryBase }}>
                            {unit}
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              );
            }
            const { main, unit } = valueParts(r.value);
            return (
              <div
                key={r.key}
                data-hud-free-text={r.small ? "" : undefined}
                style={{
                  display: "flex",
                  gap: 5,
                  whiteSpace: "nowrap",
                  fontSize: r.small ? textBase : base,
                }}
              >
                {r.label && <span style={{ color: textColor(r.labelColor), fontWeight: 600 }}>{r.label}</span>}
                <span style={{ color: textColor(r.valueColor) }}>
                  <span>{main}</span>
                  {!r.small && unit && (
                    <span data-hud-value-unit style={{ fontSize: secondaryBase }}>
                      {unit}
                    </span>
                  )}
                </span>
              </div>
            );
        })}
      </div>
    </div>
    {clips && (
      <div
        data-testid="hud-preview-clipping-warning"
        style={{
          padding: "4px 7px",
          borderRadius: 6,
          color: "#ffcf8a",
          background: "rgba(255,180,84,0.08)",
          fontSize: 10,
          lineHeight: 1.3,
        }}
      >
        {t("hud.preview.clipped")}
      </div>
    )}
    </div>
  );
};
