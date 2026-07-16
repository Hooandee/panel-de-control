// Frontend mirror of the HUD model (backend: py_modules/mangohud/config.py). The
// preview renders exactly what MangoHud will show — the ordered items, coloured per
// category, honouring custom labels/separators/font — so it never lies about the
// real overlay.

export type MetricId =
  | "fps" | "frametime" | "time"
  | "gpu" | "gpu_temp" | "gpu_clock" | "gpu_power" | "vram" | "gpu_name"
  | "cpu" | "cpu_temp" | "cpu_clock" | "cpu_power" | "cores"
  | "ram" | "swap" | "io_read" | "io_write"
  | "battery" | "battery_watt" | "battery_time" | "device_battery"
  | "resolution" | "arch" | "wine" | "engine_version" | "fan"
  // Panel de Control plugin-state metrics (value baked into the custom_text row by
  // the backend at apply time; see py_modules/mangohud/pdc_metrics.py).
  | "pdc_tdp" | "pdc_tdp_learn" | "pdc_auto_tdp" | "pdc_fan" | "pdc_fan_rpm"
  | "pdc_eco" | "pdc_profile" | "pdc_power" | "pdc_charge" | "pdc_bat_health"
  | "pdc_smt" | "pdc_boost" | "pdc_cores" | "pdc_gpu_clock" | "pdc_model";

// Colour keys mirror config.py. MangoHud colours by CATEGORY, not per element:
// gpu/cpu/vram/ram/battery tint that category's LABEL word; `text` tints every
// metric VALUE + all custom text + the vertical divider; `fps` is the (solid) fps
// number; `frametime` the frametime number; `background`/`outline` the box + outline.
export type ColorKey =
  | "text" | "fps" | "gpu" | "cpu" | "vram" | "ram" | "battery"
  | "frametime" | "background" | "outline";
export type HudPosition = "top-left" | "top-right" | "bottom-left" | "bottom-right";
export type HudLayout = "vertical" | "horizontal";
export type TempUnit = "c" | "f";
export type MetricGroup = "fps" | "gpu" | "cpu" | "temps" | "mem" | "battery" | "system" | "pdc";
// GPU, CPU and BATTERY render as ONE row each (a category label + a column per
// sub-metric) and are GATED by their parent (dropping the group drops its sub-metrics);
// the elements list mirrors that with a single expandable container per group.
export type BlockGroup = "gpu" | "cpu" | "battery";
export const BLOCK_GROUPS: BlockGroup[] = ["gpu", "cpu", "battery"];

// MangoHud can only relabel these three lines; a label on any other metric is
// ignored (mirrors _LABEL_DIRECTIVE in config.py). The pdc metrics are ALSO
// labellable — they render as a custom_text line whose label we emit ourselves.
export const PDC_IDS: MetricId[] = [
  "pdc_tdp", "pdc_tdp_learn", "pdc_auto_tdp", "pdc_fan", "pdc_fan_rpm", "pdc_eco",
  "pdc_profile", "pdc_power", "pdc_charge", "pdc_bat_health", "pdc_smt", "pdc_boost",
  "pdc_cores", "pdc_gpu_clock", "pdc_model",
];
export const LABELABLE: MetricId[] = ["fps", "cpu", "gpu", ...PDC_IDS];
export const canLabel = (id: MetricId): boolean => LABELABLE.includes(id);

export type SpacerSize = "small" | "medium" | "large";
export const SPACER_SIZES: SpacerSize[] = ["small", "medium", "large"];
// Blank rows per spacer size (mirrors _SPACER_LINES in config.py).
export const SPACER_LINES: Record<SpacerSize, number> = { small: 1, medium: 2, large: 3 };

export type HudItem =
  | { kind: "metric"; id: MetricId; label?: string }
  | { kind: "text"; id: string; text: string }
  | { kind: "separator"; id: string }
  | { kind: "spacer"; id: string; size: SpacerSize };

export interface HudModel {
  enabled: boolean;
  items: HudItem[];
  position: HudPosition;
  /** Global font size in px (MangoHud has no per-element size). */
  fontSize: number;
  /** Secondary/small text size in px (labels, custom_text, superscripts). */
  fontSizeText: number;
  layout: HudLayout;
  noSmallFont: boolean;
  tempUnit: TempUnit;
  textOutline: boolean;
  separatorColor: string | null;
  colors: Record<ColorKey, string>;
  background: { alpha: number; roundCorners: boolean };
  // ---- Avanzado (global style) ----
  /** Vertical padding between rows (cellpadding_y). */
  cellpaddingY: number;
  /** hud_compact — condensed layout. */
  compact: boolean;
  /** hud_no_margin — drop the outer margin. */
  noMargin: boolean;
  /** Position nudge in px (offset_x / offset_y). */
  offsetX: number;
  offsetY: number;
  /** Foreground/text opacity (alpha), distinct from background.alpha. */
  alpha: number;
  /** Global font multiplier (font_scale). */
  fontScale: number;
}

export interface HudState {
  supported: boolean;
  running: boolean;
  model: HudModel;
  catalog: MetricId[];
  presets: Record<string, MetricId[]>;
}

interface MetricMeta {
  id: MetricId;
  /** Colour key that tints this metric's LABEL word (MangoHud colours by category). */
  category: ColorKey;
  /** Render/block group (drives blockGroupOf + the GPU/CPU/battery collapsed rows). */
  group: MetricGroup;
  /** Catalog-only group for the "+" picker, when it should differ from `group`
   *  (e.g. temps live in the GPU/CPU render blocks but list under "Temperaturas").
   *  Defaults to `group`. */
  catalogGroup?: MetricGroup;
  /** Short label MangoHud shows for the line (colour-tinted). fps/cpu/gpu are
   *  overridable by the user; the rest are fixed. */
  label: string;
  /** Representative value for the live preview (MangoHud fills the real number). */
  value: string;
}

// Catalog order == default row order == the order the pill catalog shows.
export const METRICS: MetricMeta[] = [
  // FPS
  { id: "fps", category: "fps", group: "fps", label: "FPS", value: "60" },
  { id: "frametime", category: "frametime", group: "fps", label: "FRAME", value: "16.6ms" },
  { id: "time", category: "text", group: "fps", label: "TIME", value: "22:14" },
  // GPU
  { id: "gpu", category: "gpu", group: "gpu", label: "GPU", value: "74%" },
  { id: "gpu_temp", category: "gpu", group: "gpu", catalogGroup: "temps", label: "GPU°", value: "68°C" },
  { id: "gpu_clock", category: "gpu", group: "gpu", label: "GCLK", value: "2200MHz" },
  { id: "gpu_power", category: "gpu", group: "gpu", label: "GPU W", value: "18W" },
  { id: "vram", category: "vram", group: "gpu", label: "VRAM", value: "4.1G" },
  { id: "gpu_name", category: "gpu", group: "gpu", label: "GPU", value: "Radeon" },
  // CPU
  { id: "cpu", category: "cpu", group: "cpu", label: "CPU", value: "41%" },
  { id: "cpu_temp", category: "cpu", group: "cpu", catalogGroup: "temps", label: "CPU°", value: "62°C" },
  { id: "cpu_clock", category: "cpu", group: "cpu", label: "CCLK", value: "3400MHz" },
  { id: "cpu_power", category: "cpu", group: "cpu", label: "CPU W", value: "12W" },
  { id: "cores", category: "cpu", group: "cpu", label: "CORE", value: "▂▄▆▅▃▆" },
  // Memory
  { id: "ram", category: "ram", group: "mem", label: "RAM", value: "9.2G" },
  { id: "swap", category: "ram", group: "mem", label: "SWAP", value: "0.2G" },
  { id: "io_read", category: "ram", group: "mem", label: "IO R", value: "1.2" },
  { id: "io_write", category: "ram", group: "mem", label: "IO W", value: "0.4" },
  // Battery
  { id: "battery", category: "battery", group: "battery", label: "BAT", value: "82%" },
  { id: "battery_watt", category: "battery", group: "battery", label: "BAT W", value: "12W" },
  { id: "battery_time", category: "battery", group: "battery", label: "BAT", value: "2:41" },
  { id: "device_battery", category: "battery", group: "battery", label: "GP", value: "70%" },
  // System
  { id: "resolution", category: "text", group: "system", label: "RES", value: "1920x1080" },
  { id: "arch", category: "text", group: "system", label: "ARCH", value: "x86_64" },
  { id: "wine", category: "text", group: "system", label: "WINE", value: "9.0" },
  { id: "engine_version", category: "text", group: "system", label: "ENG", value: "vk1.3" },
  { id: "fan", category: "text", group: "system", label: "FAN", value: "3200rpm" },
  // Panel de Control plugin state. Category "text" (they're custom_text lines); the
  // preview value is a representative sample of what the backend writes live. Labels
  // mirror the defaults in config.py (_PDC_LABEL) so the preview is faithful.
  { id: "pdc_tdp", category: "text", group: "pdc", label: "TDP", value: "Auto 18W" },
  { id: "pdc_tdp_learn", category: "text", group: "pdc", label: "Banda", value: "13-19W" },
  { id: "pdc_auto_tdp", category: "text", group: "pdc", label: "Auto", value: "On" },
  { id: "pdc_fan", category: "text", group: "pdc", label: "Vent.", value: "Adaptativo" },
  { id: "pdc_fan_rpm", category: "text", group: "pdc", label: "RPM", value: "3200" },
  { id: "pdc_eco", category: "text", group: "pdc", label: "Descarga", value: "Inactivo" },
  { id: "pdc_profile", category: "text", group: "pdc", label: "Perfil", value: "Global" },
  { id: "pdc_power", category: "text", group: "pdc", label: "Consumo", value: "20W 92%" },
  { id: "pdc_charge", category: "text", group: "pdc", label: "Limite", value: "80%" },
  { id: "pdc_bat_health", category: "text", group: "pdc", label: "Salud", value: "96%" },
  { id: "pdc_smt", category: "text", group: "pdc", label: "SMT", value: "On" },
  { id: "pdc_boost", category: "text", group: "pdc", label: "Boost", value: "On" },
  { id: "pdc_cores", category: "text", group: "pdc", label: "Nucleos", value: "6/8" },
  { id: "pdc_gpu_clock", category: "text", group: "pdc", label: "GPU MHz", value: "800-2700" },
  { id: "pdc_model", category: "text", group: "pdc", label: "Equipo", value: "Legion Go 2" },
];

const META: Record<MetricId, MetricMeta> = METRICS.reduce(
  (acc, m) => ((acc[m.id] = m), acc),
  {} as Record<MetricId, MetricMeta>,
);

export const metricMeta = (id: MetricId): MetricMeta => META[id];

// Catalog groups for the pill UI, in display order.
export const GROUPS: { key: MetricGroup; ids: MetricId[] }[] = (
  ["fps", "gpu", "cpu", "temps", "mem", "battery", "system", "pdc"] as MetricGroup[]
).map((key) => ({ key, ids: METRICS.filter((m) => (m.catalogGroup ?? m.group) === key).map((m) => m.id) }));

export const DEFAULT_MODEL: HudModel = {
  enabled: false,
  items: (["fps", "gpu", "cpu", "ram", "battery"] as MetricId[]).map((id) => ({ kind: "metric", id })),
  position: "top-left",
  fontSize: 24,
  fontSizeText: 24,
  layout: "vertical",
  noSmallFont: false,
  tempUnit: "c",
  textOutline: true,
  separatorColor: null,
  colors: {
    text: "ffffff",
    fps: "ffffff",
    gpu: "6ee7b7",
    cpu: "7dd3fc",
    vram: "c4b5fd",
    ram: "f0abfc",
    battery: "fca5a5",
    frametime: "ffd580",
    background: "000000",
    outline: "000000",
  },
  background: { alpha: 0.5, roundCorners: true },
  cellpaddingY: -0.085,
  compact: false,
  noMargin: false,
  offsetX: 0,
  offsetY: 0,
  alpha: 1.0,
  fontScale: 1.0,
};

// The colour controls the "Estilo general" section shows, in display order.
// (Each corresponds to a MangoHud colour directive — see config.py.)
export const COLOR_KEYS: ColorKey[] = [
  "text", "fps", "gpu", "cpu", "vram", "ram", "battery", "frametime", "background", "outline",
];

export const PRESETS: Record<string, MetricId[]> = {
  minimal: ["fps"],
  balanced: ["fps", "gpu", "cpu", "ram", "battery"],
  full: [
    "fps", "frametime", "gpu", "gpu_temp", "gpu_power", "vram",
    "cpu", "cpu_temp", "cpu_power", "ram", "battery", "time",
  ],
};

// ---- Colour maths (pure, no @decky/ui → unit-testable) ----
// The Steam CEF native <input type=color> is dead, so the ColorPicker uses RGB
// sliders + a hex field built on these. Hex is always 6 chars, no leading '#'.

export interface Rgb { r: number; g: number; b: number; }

const clampByte = (n: number): number => Math.max(0, Math.min(255, Math.round(n)));

export function rgbToHex({ r, g, b }: Rgb): string {
  return [r, g, b].map((n) => clampByte(n).toString(16).padStart(2, "0")).join("");
}

/** Parse a hex colour to RGB. Accepts an optional '#' and 3- or 6-digit hex;
 *  falls back to black on anything unparseable (never throws). */
export function hexToRgb(hex: string): Rgb {
  let h = (hex || "").trim().replace(/^#/, "").toLowerCase();
  if (/^[0-9a-f]{3}$/.test(h)) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-f]{6}$/.test(h)) return { r: 0, g: 0, b: 0 };
  return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
}

/** Normalise arbitrary user hex input to a clean 6-digit lowercase hex, or null
 *  if it can't be parsed (so the caller can reject a half-typed value). */
export function normalizeHex(hex: string): string | null {
  const h = (hex || "").trim().replace(/^#/, "").toLowerCase();
  if (/^[0-9a-f]{3}$/.test(h)) return h.split("").map((c) => c + c).join("");
  return /^[0-9a-f]{6}$/.test(h) ? h : null;
}

// MangoHud renders GPU and CPU as ONE row each — the category label once, then a
// column per metric (e.g. "GPU 74% 68° 2200 18W"). Everything else is its own line.
const GROUP_LABEL: Partial<Record<MetricGroup, string>> = { gpu: "GPU", cpu: "CPU", battery: "BAT" };
const GROUP_COLOR: Record<BlockGroup, ColorKey> = { gpu: "gpu", cpu: "cpu", battery: "battery" };

export type PreviewRow =
  | { kind: "group"; key: string; group: BlockGroup; label: string; labelColor: string; valueColor: string; cells: string[] }
  | { kind: "line"; key: string; label: string; value: string; labelColor: string; valueColor: string; small: boolean }
  | { kind: "separator"; key: string }
  | { kind: "spacer"; key: string; size: SpacerSize };

/** The colour key that tints a metric's VALUE: fps + frametime are their own
 *  (solid) colours; every other value uses the global text colour — mirroring what
 *  MangoHud actually does (fps_color / frametime_color / text_color). */
function valueColorKey(id: MetricId): ColorKey {
  if (id === "fps") return "fps";
  if (id === "frametime") return "frametime";
  return "text";
}

/** The rows the preview draws, faithful to MangoHud: consecutive GPU/CPU metrics
 *  collapse into ONE row (label tinted by category, a cell per value in text
 *  colour); other metrics and custom text are single lines; separators draw a
 *  divider. A labelled metric (fps/cpu/gpu) uses its custom label. */
export function previewRows(model: HudModel): PreviewRow[] {
  const rows: PreviewRow[] = [];
  const c = (key: ColorKey) => `#${model.colors[key]}`;
  model.items.forEach((it, i) => {
    if (it.kind === "separator") {
      rows.push({ kind: "separator", key: `s:${it.id}:${i}` });
      return;
    }
    if (it.kind === "spacer") {
      rows.push({ kind: "spacer", key: `sp:${it.id}:${i}`, size: it.size });
      return;
    }
    if (it.kind === "text") {
      rows.push({ kind: "line", key: `t:${it.id}:${i}`, label: "", value: it.text, labelColor: c("text"), valueColor: c("text"), small: !model.noSmallFont });
      return;
    }
    const meta = META[it.id];
    const group = blockGroupOf(it.id);
    if (group) {
      const last = rows[rows.length - 1];
      if (last && last.kind === "group" && last.group === group) {
        last.cells.push(meta.value);
        if (canLabel(it.id) && it.label) last.label = it.label;
      } else {
        rows.push({
          kind: "group",
          key: `g:${group}:${i}`,
          group,
          label: canLabel(it.id) && it.label ? it.label : (GROUP_LABEL[group] as string),
          labelColor: c(GROUP_COLOR[group]),
          valueColor: c("text"),
          cells: [meta.value],
        });
      }
      return;
    }
    rows.push({
      kind: "line",
      key: `m:${it.id}`,
      label: canLabel(it.id) && it.label ? it.label : meta.label,
      value: meta.value,
      labelColor: c(meta.category),
      valueColor: c(valueColorKey(it.id)),
      small: false,
    });
  });
  return rows;
}

export const hasMetric = (items: HudItem[], id: MetricId): boolean =>
  items.some((it) => it.kind === "metric" && it.id === id);

/** The block a metric belongs to (GPU/CPU render as one merged row), or null for a
 *  standalone metric. Based on the metric's group so vram/gpu_name join the GPU row. */
export function blockGroupOf(id: MetricId): BlockGroup | null {
  const g = META[id].group;
  return (BLOCK_GROUPS as MetricGroup[]).includes(g) ? (g as BlockGroup) : null;
}

/** All metric ids that belong to a block group (its expandable sub-metrics). */
export const blockMetricIds = (group: BlockGroup): MetricId[] =>
  METRICS.filter((m) => m.group === group).map((m) => m.id);

export const hasBlock = (items: HudItem[], group: BlockGroup): boolean =>
  items.some((it) => it.kind === "metric" && blockGroupOf(it.id) === group);

/** Add a metric. A block-group metric is inserted right after the last member of
 *  its block so the group stays contiguous (== how the merged row renders); other
 *  metrics append. No-op if already present. */
export function addMetricItem(items: HudItem[], id: MetricId): HudItem[] {
  if (hasMetric(items, id)) return items;
  const group = blockGroupOf(id);
  if (group) {
    let last = -1;
    items.forEach((it, i) => {
      if (it.kind === "metric" && blockGroupOf(it.id) === group) last = i;
    });
    if (last >= 0) {
      const next = [...items];
      next.splice(last + 1, 0, { kind: "metric", id });
      return next;
    }
  }
  return [...items, { kind: "metric", id }];
}

/** Add a metric if absent, remove it if present. */
export function toggleMetricItem(items: HudItem[], id: MetricId): HudItem[] {
  return hasMetric(items, id)
    ? items.filter((it) => !(it.kind === "metric" && it.id === id))
    : addMetricItem(items, id);
}

export const addTextItem = (items: HudItem[], id: string, text: string): HudItem[] =>
  [...items, { kind: "text", id, text }];

export const addSeparator = (items: HudItem[], id: string): HudItem[] =>
  [...items, { kind: "separator", id }];

export const addSpacer = (items: HudItem[], id: string, size: SpacerSize = "small"): HudItem[] =>
  [...items, { kind: "spacer", id, size }];

/** Set the size of the spacer item at flat `index` (no-op if it isn't a spacer). */
export function setSpacerSizeAt(items: HudItem[], index: number, size: SpacerSize): HudItem[] {
  const it = items[index];
  if (!it || it.kind !== "spacer") return items;
  const next = [...items];
  next[index] = { ...it, size };
  return next;
}

// ---- Elements list as blocks (GPU/CPU collapse to one expandable row each) ----

export type ListRow =
  | { kind: "block"; group: BlockGroup; ids: MetricId[]; start: number; len: number }
  | { kind: "metric"; id: MetricId; index: number }
  | { kind: "text"; id: string; text: string; index: number }
  | { kind: "separator"; id: string; index: number }
  | { kind: "spacer"; id: string; size: SpacerSize; index: number };

/** The elements list as rows: a contiguous run of same-block-group metrics becomes
 *  one block row (matching the merged preview row); everything else is its own row. */
export function listRows(items: HudItem[]): ListRow[] {
  const rows: ListRow[] = [];
  items.forEach((it, i) => {
    if (it.kind === "text") { rows.push({ kind: "text", id: it.id, text: it.text, index: i }); return; }
    if (it.kind === "separator") { rows.push({ kind: "separator", id: it.id, index: i }); return; }
    if (it.kind === "spacer") { rows.push({ kind: "spacer", id: it.id, size: it.size, index: i }); return; }
    const group = blockGroupOf(it.id);
    if (group) {
      const last = rows[rows.length - 1];
      if (last && last.kind === "block" && last.group === group && last.start + last.len === i) {
        last.ids.push(it.id);
        last.len += 1;
      } else {
        rows.push({ kind: "block", group, ids: [it.id], start: i, len: 1 });
      }
      return;
    }
    rows.push({ kind: "metric", id: it.id, index: i });
  });
  return rows;
}

/** The item span [start, start+len) each list row occupies in the flat items. */
function rowSpans(items: HudItem[]): { start: number; len: number }[] {
  return listRows(items).map((r) =>
    r.kind === "block" ? { start: r.start, len: r.len } : { start: r.index, len: 1 },
  );
}

/** Move a whole list row (block or single) by `delta` (+1 down / -1 up), clamped. */
export function moveRow(items: HudItem[], rowIndex: number, delta: number): HudItem[] {
  const spans = rowSpans(items);
  const a = rowIndex;
  const b = rowIndex + delta;
  if (b < 0 || b >= spans.length || delta === 0) return items;
  const [lo, hi] = a < b ? [a, b] : [b, a];
  const first = spans[lo];
  const second = spans[hi]; // adjacent rows → first.start+first.len === second.start
  return [
    ...items.slice(0, first.start),
    ...items.slice(second.start, second.start + second.len),
    ...items.slice(first.start, first.start + first.len),
    ...items.slice(second.start + second.len),
  ];
}

/** Remove a whole list row (all members of a block, or a single item). */
export function removeRow(items: HudItem[], rowIndex: number): HudItem[] {
  const span = rowSpans(items)[rowIndex];
  if (!span) return items;
  return [...items.slice(0, span.start), ...items.slice(span.start + span.len)];
}

/** Set (or clear) the custom label on the metric with id `id`. No-op on a metric
 *  MangoHud can't relabel (only fps/cpu/gpu). Used by the block/line editor. */
export function setMetricLabel(items: HudItem[], id: MetricId, label: string): HudItem[] {
  if (!canLabel(id)) return items;
  const trimmed = label.trim();
  return items.map((it) =>
    it.kind === "metric" && it.id === id
      ? (trimmed ? { kind: "metric", id, label } : { kind: "metric", id })
      : it,
  );
}

/** Set the text on a text item at flat `index`. */
export function setTextAt(items: HudItem[], index: number, text: string): HudItem[] {
  const it = items[index];
  if (!it || it.kind !== "text") return items;
  const next = [...items];
  next[index] = { ...it, text };
  return next;
}
