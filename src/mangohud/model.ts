// Frontend mirror of the HUD model (backend: py_modules/mangohud/config.py). The
// preview renders exactly what MangoHud will show — the ordered items, coloured per
// category, honouring custom labels/separators/font — so it never lies about the
// real overlay.

export type MetricId =
  | "fps" | "fps_metrics" | "frametime" | "frame_count" | "show_fps_limit" | "time"
  | "gpu" | "gpu_temp" | "gpu_junction_temp" | "gpu_clock" | "gpu_mem_clock"
  | "gpu_mem_temp" | "gpu_power" | "gpu_voltage" | "gpu_fan" | "gpu_efficiency"
  | "vram" | "proc_vram" | "gpu_name"
  | "cpu" | "cpu_temp" | "cpu_clock" | "cpu_power" | "cpu_efficiency" | "cores"
  | "ram" | "procmem" | "swap" | "io_read" | "io_write"
  | "battery" | "battery_watt" | "battery_time" | "device_battery"
  | "resolution" | "refresh_rate" | "arch" | "wine" | "winesync" | "engine_version"
  | "vulkan_driver" | "present_mode" | "display_server" | "gamemode" | "vkbasalt"
  | "fsr" | "hdr" | "fan" | "network" | "media_player" | "version"
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
  | "frametime" | "network" | "background" | "outline";
export type HudPosition = "top-left" | "top-right" | "bottom-left" | "bottom-right";
export type HudLayout = "vertical" | "horizontal";
export type HudLocale = "es" | "en";
export type TempUnit = "c" | "f";
export type MetricGroup = "fps" | "gpu" | "cpu" | "temps" | "mem" | "battery" | "system" | "pdc";
// GPU, CPU and BATTERY render as ONE row each (a category label + a column per
// sub-metric) and are GATED by their parent (dropping the group drops its sub-metrics);
// the elements list mirrors that with a single expandable container per group.
export type BlockGroup = "gpu" | "cpu" | "battery";
export const BLOCK_GROUPS: BlockGroup[] = ["gpu", "cpu", "battery"];
const BLOCK_GROUP_SET = new Set<BlockGroup>(BLOCK_GROUPS);
export const isBlockGroup = (group: string): group is BlockGroup =>
  BLOCK_GROUP_SET.has(group as BlockGroup);

// MangoHud can only relabel these three lines; a label on any other metric is
// ignored (mirrors _LABEL_DIRECTIVE in config.py). The pdc metrics are ALSO
// labellable — they render as a custom_text line whose label we emit ourselves.
export const PDC_IDS: MetricId[] = [
  "pdc_tdp", "pdc_tdp_learn", "pdc_auto_tdp", "pdc_fan", "pdc_fan_rpm", "pdc_eco",
  "pdc_profile", "pdc_power", "pdc_charge", "pdc_bat_health", "pdc_smt", "pdc_boost",
  "pdc_cores", "pdc_gpu_clock", "pdc_model",
];
const PDC_ID_SET = new Set<MetricId>(PDC_IDS);
export const LABELABLE: MetricId[] = ["fps", "cpu", "gpu", ...PDC_IDS];
const LABELABLE_SET = new Set<MetricId>(LABELABLE);
export const canLabel = (id: MetricId): boolean => LABELABLE_SET.has(id);

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
  locale: HudLocale;
  items: HudItem[];
  position: HudPosition;
  /** Main metric font size in px. */
  fontSize: number;
  /** Auxiliary metrics and custom text size in px. */
  fontSizeSecondary: number;
  /** Media metadata font size in px. */
  fontSizeText: number;
  layout: HudLayout;
  noSmallFont: boolean;
  tempUnit: TempUnit;
  textOutline: boolean;
  textOutlineThickness: number;
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

export type HudCapability = "ready" | "unsupported" | "inactive" | "ambiguous";
export type HudApplyStatus =
  | "disabled"
  | "pending"
  | "written"
  | "reload_requested"
  | "unavailable"
  | "ambiguous"
  | "conflict"
  | "failed";

export interface HudConflict {
  path: string;
  expectedHash: string | null;
  actualHash: string | null;
}

export interface HudState {
  supported: boolean;
  running: boolean;
  capability: HudCapability;
  applyStatus: HudApplyStatus;
  conflict: HudConflict | null;
  model: HudModel;
  values: Partial<Record<MetricId, string>>;
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
  { id: "fps_metrics", category: "fps", group: "fps", label: "FPS AVG", value: "58" },
  { id: "frametime", category: "frametime", group: "fps", label: "FRAME", value: "16.6ms" },
  { id: "frame_count", category: "text", group: "fps", label: "FRAMES", value: "12042" },
  { id: "show_fps_limit", category: "text", group: "fps", label: "LIMIT", value: "60" },
  { id: "time", category: "text", group: "fps", label: "TIME", value: "22:14" },
  // GPU
  { id: "gpu", category: "gpu", group: "gpu", label: "GPU", value: "74%" },
  { id: "gpu_temp", category: "gpu", group: "gpu", catalogGroup: "temps", label: "GPU°", value: "68°C" },
  { id: "gpu_junction_temp", category: "gpu", group: "gpu", catalogGroup: "temps", label: "JUNC°", value: "78°C" },
  { id: "gpu_clock", category: "gpu", group: "gpu", label: "GCLK", value: "2200MHz" },
  { id: "gpu_mem_clock", category: "gpu", group: "gpu", label: "MCLK", value: "1800MHz" },
  { id: "gpu_mem_temp", category: "gpu", group: "gpu", catalogGroup: "temps", label: "VRAM°", value: "72°C" },
  { id: "gpu_power", category: "gpu", group: "gpu", label: "GPU W", value: "18W" },
  { id: "gpu_voltage", category: "gpu", group: "gpu", label: "GPU V", value: "0.95V" },
  { id: "gpu_fan", category: "gpu", group: "gpu", label: "GPU FAN", value: "1800rpm" },
  { id: "gpu_efficiency", category: "gpu", group: "gpu", label: "GPU EFF", value: "3.2" },
  { id: "vram", category: "vram", group: "gpu", label: "VRAM", value: "4.1G" },
  { id: "proc_vram", category: "vram", group: "gpu", label: "PROC VRAM", value: "3.4G" },
  { id: "gpu_name", category: "gpu", group: "gpu", label: "GPU", value: "Radeon" },
  // CPU
  { id: "cpu", category: "cpu", group: "cpu", label: "CPU", value: "41%" },
  { id: "cpu_temp", category: "cpu", group: "cpu", catalogGroup: "temps", label: "CPU°", value: "62°C" },
  { id: "cpu_clock", category: "cpu", group: "cpu", label: "CCLK", value: "3400MHz" },
  { id: "cpu_power", category: "cpu", group: "cpu", label: "CPU W", value: "12W" },
  { id: "cpu_efficiency", category: "cpu", group: "cpu", label: "CPU EFF", value: "2.8" },
  { id: "cores", category: "cpu", group: "cpu", label: "CORE", value: "▂▄▆▅▃▆" },
  // Memory
  { id: "ram", category: "ram", group: "mem", label: "RAM", value: "9.2G" },
  { id: "procmem", category: "ram", group: "mem", label: "PROC RAM", value: "5.4G" },
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
  { id: "refresh_rate", category: "text", group: "system", label: "HZ", value: "120Hz" },
  { id: "arch", category: "text", group: "system", label: "ARCH", value: "x86_64" },
  { id: "wine", category: "text", group: "system", label: "WINE", value: "9.0" },
  { id: "winesync", category: "text", group: "system", label: "SYNC", value: "esync" },
  { id: "engine_version", category: "text", group: "system", label: "ENG", value: "vk1.3" },
  { id: "vulkan_driver", category: "text", group: "system", label: "VK", value: "RADV" },
  { id: "present_mode", category: "text", group: "system", label: "PRESENT", value: "Mailbox" },
  { id: "display_server", category: "text", group: "system", label: "DISPLAY", value: "Wayland" },
  { id: "gamemode", category: "text", group: "system", label: "GAMEMODE", value: "On" },
  { id: "vkbasalt", category: "text", group: "system", label: "VKBASALT", value: "Off" },
  { id: "fsr", category: "text", group: "system", label: "FSR", value: "On" },
  { id: "hdr", category: "text", group: "system", label: "HDR", value: "On" },
  { id: "fan", category: "text", group: "system", label: "FAN", value: "3200rpm" },
  { id: "network", category: "network", group: "system", label: "NET", value: "4.2M" },
  { id: "media_player", category: "text", group: "system", label: "MEDIA", value: "Playing" },
  { id: "version", category: "text", group: "system", label: "MANGOHUD", value: "0.8" },
  // Panel de Control plugin state. Category "text" because these are custom_text
  // lines. Their values come from the backend snapshot; "-" is the honest fallback.
  { id: "pdc_tdp", category: "text", group: "pdc", label: "TDP", value: "-" },
  { id: "pdc_tdp_learn", category: "text", group: "pdc", label: "Banda", value: "-" },
  { id: "pdc_auto_tdp", category: "text", group: "pdc", label: "Auto", value: "-" },
  { id: "pdc_fan", category: "text", group: "pdc", label: "Vent.", value: "-" },
  { id: "pdc_fan_rpm", category: "text", group: "pdc", label: "RPM", value: "-" },
  { id: "pdc_eco", category: "text", group: "pdc", label: "Descarga", value: "-" },
  { id: "pdc_profile", category: "text", group: "pdc", label: "Perfil", value: "-" },
  { id: "pdc_power", category: "text", group: "pdc", label: "Consumo", value: "-" },
  { id: "pdc_charge", category: "text", group: "pdc", label: "Limite", value: "-" },
  { id: "pdc_bat_health", category: "text", group: "pdc", label: "Salud", value: "-" },
  { id: "pdc_smt", category: "text", group: "pdc", label: "SMT", value: "-" },
  { id: "pdc_boost", category: "text", group: "pdc", label: "Boost", value: "-" },
  { id: "pdc_cores", category: "text", group: "pdc", label: "Nucleos", value: "-" },
  { id: "pdc_gpu_clock", category: "text", group: "pdc", label: "GPU MHz", value: "-" },
  { id: "pdc_model", category: "text", group: "pdc", label: "Equipo", value: "-" },
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
  locale: "es",
  items: (["fps", "gpu", "cpu", "ram", "battery"] as MetricId[]).map((id) => ({ kind: "metric", id })),
  position: "top-left",
  fontSize: 24,
  fontSizeSecondary: 13,
  fontSizeText: 24,
  layout: "vertical",
  noSmallFont: false,
  tempUnit: "c",
  textOutline: true,
  textOutlineThickness: 1.0,
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
    network: "a5b4fc",
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
  "text", "fps", "gpu", "cpu", "vram", "ram", "battery", "frametime", "network", "background", "outline",
];

export const PRESETS: Record<string, MetricId[]> = {
  minimal: ["fps"],
  balanced: ["fps", "gpu", "cpu", "ram", "battery"],
  full: [
    "fps", "frametime", "gpu", "gpu_temp", "gpu_power", "vram",
    "cpu", "cpu_temp", "cpu_power", "ram", "battery", "time",
  ],
};

export function matchingPresetKey(
  items: HudItem[],
  presets: Readonly<Record<string, readonly MetricId[]>>,
): string | null {
  const selected = items.flatMap((item) => item.kind === "metric" ? [item.id] : []);
  for (const [key, preset] of Object.entries(presets)) {
    if (
      selected.length === preset.length
      && selected.every((id, index) => preset[index] === id)
    ) {
      return key;
    }
  }
  return null;
}

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

export type PreviewFontRole = "main" | "auxiliary" | "media";

export type PreviewRow =
  | { kind: "group"; key: string; group: BlockGroup; label: string; labelColor: string; valueColor: string; cells: string[] }
  | { kind: "line"; key: string; label: string; value: string; labelColor: string; valueColor: string; fontRole: PreviewFontRole }
  | { kind: "separator"; key: string }
  | { kind: "spacer"; key: string; size: SpacerSize };

const AUXILIARY_METRICS = new Set<MetricId>([
  "gpu_name", "engine_version", "vulkan_driver", "arch", "wine", "resolution",
  "show_fps_limit", "gamemode", "vkbasalt", "frame_count", "refresh_rate",
  "winesync", "present_mode", "display_server",
]);

export interface PreviewFontSizes {
  main: number;
  small: number;
  auxiliary: number;
  media: number;
}

const previewPx = (size: number, scale: number): number =>
  Math.max(1, Number((size * scale * 0.5).toFixed(2)));

export function previewFontSizes(model: HudModel): PreviewFontSizes {
  return {
    main: previewPx(model.fontSize, model.fontScale),
    small: previewPx(
      model.noSmallFont ? model.fontSize : model.fontSize * 0.55,
      model.fontScale,
    ),
    auxiliary: previewPx(
      Math.min(model.fontSizeSecondary, model.fontSize),
      model.fontScale,
    ),
    media: previewPx(model.fontSizeText * 0.55, model.fontScale),
  };
}

/** The colour key that tints a metric's VALUE: fps + frametime are their own
 *  (solid) colours; every other value uses the global text colour — mirroring what
 *  MangoHud actually does (fps_color / frametime_color / text_color). */
function valueColorKey(id: MetricId): ColorKey {
  if (id === "fps") return "fps";
  if (id === "frametime") return "frametime";
  return "text";
}

function previewValue(id: MetricId, model: HudModel): string {
  if (model.tempUnit !== "f") return META[id].value;
  if (id === "gpu_temp") return "154°F";
  if (id === "gpu_junction_temp") return "172°F";
  if (id === "gpu_mem_temp") return "162°F";
  if (id === "cpu_temp") return "144°F";
  return META[id].value;
}

/** The rows the preview draws, faithful to MangoHud: consecutive GPU/CPU metrics
 *  collapse into ONE row (label tinted by category, a cell per value in text
 *  colour); other metrics and custom text are single lines; separators draw a
 *  divider. A labelled metric (fps/cpu/gpu) uses its custom label. */
export function previewRows(
  model: HudModel,
  values: Partial<Record<MetricId, string>> = {},
): PreviewRow[] {
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
      rows.push({ kind: "line", key: `t:${it.id}:${i}`, label: "", value: it.text, labelColor: c("text"), valueColor: c("text"), fontRole: "auxiliary" });
      return;
    }
    const meta = META[it.id];
    const value = PDC_ID_SET.has(it.id)
      ? values[it.id] ?? "-"
      : previewValue(it.id, model);
    const group = blockGroupOf(it.id);
    if (group) {
      const last = rows[rows.length - 1];
      if (last && last.kind === "group" && last.group === group) {
        last.cells.push(value);
        if (canLabel(it.id) && it.label) last.label = it.label;
      } else {
        rows.push({
          kind: "group",
          key: `g:${group}:${i}`,
          group,
          label: canLabel(it.id) && it.label ? it.label : (GROUP_LABEL[group] as string),
          labelColor: c(GROUP_COLOR[group]),
          valueColor: c("text"),
          cells: [value],
        });
      }
      return;
    }
    rows.push({
      kind: "line",
      key: `m:${it.id}`,
      label: canLabel(it.id) && it.label ? it.label : meta.label,
      value,
      labelColor: c(meta.category),
      valueColor: c(valueColorKey(it.id)),
      fontRole: it.id === "media_player"
        ? "media"
        : PDC_ID_SET.has(it.id) || AUXILIARY_METRICS.has(it.id)
          ? "auxiliary"
          : "main",
    });
  });
  return rows;
}

export function previewWouldClip(
  model: HudModel,
  rows: PreviewRow[] = previewRows(model),
): boolean {
  if (model.layout === "horizontal") return false;
  const fonts = previewFontSizes(model);
  const lineHeight = fonts.main * 1.35;
  const gap = Math.max(0, Math.min(9, Math.round(1 + model.cellpaddingY * fonts.main)));
  const padding = model.noMargin ? 0 : model.compact ? 4 : 6;
  const contentHeight = rows.reduce((total, row) => {
    if (row.kind === "spacer") {
      return total + SPACER_LINES[row.size] * lineHeight;
    }
    if (row.kind === "line") return total + fonts[row.fontRole] * 1.35;
    if (row.kind === "separator") return total + fonts.auxiliary * 1.35;
    return total + lineHeight;
  }, 0);
  return contentHeight + Math.max(0, rows.length - 1) * gap + padding * 2 > 152;
}

export const hasMetric = (items: HudItem[], id: MetricId): boolean =>
  items.some((it) => it.kind === "metric" && it.id === id);

/** The block a metric belongs to (GPU/CPU render as one merged row), or null for a
 *  standalone metric. Based on the metric's group so vram/gpu_name join the GPU row. */
export function blockGroupOf(id: MetricId): BlockGroup | null {
  const g = META[id].group;
  return isBlockGroup(g) ? g : null;
}

/** All metric ids that belong to a block group (its expandable sub-metrics). */
export const blockMetricIds = (group: BlockGroup): MetricId[] =>
  METRICS.filter((m) => m.group === group).map((m) => m.id);

export const requiredMetricForBlock = (group: BlockGroup): MetricId => group;

export const isRequiredBlockMetric = (id: MetricId): boolean =>
  isBlockGroup(id);

export const hasBlock = (items: HudItem[], group: BlockGroup): boolean =>
  items.some((it) => it.kind === "metric" && blockGroupOf(it.id) === group);

/** Add a metric. A block-group metric is inserted right after the last member of
 *  its block so the group stays contiguous (== how the merged row renders); other
 *  metrics append. No-op if already present. */
export function addMetricItem(items: HudItem[], id: MetricId): HudItem[] {
  if (hasMetric(items, id)) return items;
  const group = blockGroupOf(id);
  if (group) {
    const parent = requiredMetricForBlock(group);
    const first = items.findIndex(
      (it) => it.kind === "metric" && blockGroupOf(it.id) === group,
    );
    let last = -1;
    items.forEach((it, i) => {
      if (it.kind === "metric" && blockGroupOf(it.id) === group) last = i;
    });
    if (id !== parent && !hasMetric(items, parent)) {
      const next = [...items];
      const insertAt = first >= 0 ? first : items.length;
      next.splice(insertAt, 0, { kind: "metric", id: parent });
      next.splice(last >= 0 ? last + 2 : insertAt + 1, 0, { kind: "metric", id });
      return next;
    }
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
  if (hasMetric(items, id) && isRequiredBlockMetric(id)) return items;
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
