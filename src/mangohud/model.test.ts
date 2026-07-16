import { describe, it, expect } from "vitest";
import {
  DEFAULT_MODEL,
  GROUPS,
  HudItem,
  METRICS,
  PRESETS,
  addMetricItem,
  addSeparator,
  addSpacer,
  addTextItem,
  blockGroupOf,
  blockMetricIds,
  canLabel,
  hasBlock,
  hexToRgb,
  listRows,
  moveRow,
  normalizeHex,
  previewRows,
  removeRow,
  rgbToHex,
  setMetricLabel,
  setSpacerSizeAt,
  setTextAt,
  toggleMetricItem,
} from "./model";

const metrics = (...ids: string[]): HudItem[] => ids.map((id) => ({ kind: "metric", id: id as never }));

describe("previewRows", () => {
  it("collapses consecutive same-group GPU/CPU metrics into ONE row with a cell each", () => {
    const rows = previewRows({ ...DEFAULT_MODEL, items: metrics("cpu", "cpu_temp", "cpu_power") });
    expect(rows.length).toBe(1);
    const row = rows[0];
    expect(row.kind).toBe("group");
    if (row.kind === "group") {
      expect(row.label).toBe("CPU");
      expect(row.cells).toEqual(["41%", "62°C", "12W"]);
    }
  });

  it("keeps non-mergeable metrics (fps, ram) as their own lines", () => {
    const rows = previewRows({ ...DEFAULT_MODEL, items: metrics("fps", "ram") });
    expect(rows.map((r) => r.kind)).toEqual(["line", "line"]);
    expect(rows.map((r) => (r.kind === "line" ? r.value : ""))).toEqual(["60", "9.2G"]);
  });

  it("collapses consecutive battery metrics into ONE row tinted by the battery colour", () => {
    const rows = previewRows({
      ...DEFAULT_MODEL,
      items: metrics("battery", "battery_watt", "battery_time"),
      colors: { ...DEFAULT_MODEL.colors, battery: "aabbcc" },
    });
    expect(rows.length).toBe(1);
    const row = rows[0];
    expect(row.kind).toBe("group");
    if (row.kind === "group") {
      expect(row.label).toBe("BAT");
      expect(row.labelColor).toBe("#aabbcc");
      expect(row.cells).toEqual(["82%", "12W", "2:41"]);
    }
  });

  it("does NOT merge a group broken by another item in between", () => {
    const rows = previewRows({ ...DEFAULT_MODEL, items: metrics("gpu", "fps", "gpu_temp") });
    expect(rows.map((r) => r.kind)).toEqual(["group", "line", "group"]);
  });

  it("tints a group row LABEL by its category and its VALUES by text colour", () => {
    const [row] = previewRows({
      ...DEFAULT_MODEL,
      items: metrics("gpu"),
      colors: { ...DEFAULT_MODEL.colors, gpu: "112233", text: "eeeeee" },
    });
    if (row.kind === "group") {
      expect(row.labelColor).toBe("#112233");
      expect(row.valueColor).toBe("#eeeeee");
    }
  });

  it("tints the fps value with its own (solid) colour, not text colour", () => {
    const [row] = previewRows({
      ...DEFAULT_MODEL,
      items: metrics("fps"),
      colors: { ...DEFAULT_MODEL.colors, fps: "abcdef", text: "111111" },
    });
    if (row.kind === "line") expect(row.valueColor).toBe("#abcdef");
  });

  it("tints frametime with frametime colour and other values with text colour", () => {
    const model = { ...DEFAULT_MODEL, colors: { ...DEFAULT_MODEL.colors, frametime: "222222", text: "999999" } };
    const ft = previewRows({ ...model, items: metrics("frametime") })[0];
    if (ft.kind === "line") expect(ft.valueColor).toBe("#222222");
    const time = previewRows({ ...model, items: metrics("time") })[0];
    if (time.kind === "line") expect(time.valueColor).toBe("#999999");
  });

  it("uses the custom label on a group row (gpu) and a line (fps)", () => {
    const g = previewRows({ ...DEFAULT_MODEL, items: [{ kind: "metric", id: "gpu", label: "Grafica" }] })[0];
    if (g.kind === "group") expect(g.label).toBe("Grafica");
    const f = previewRows({ ...DEFAULT_MODEL, items: [{ kind: "metric", id: "fps", label: "Cuadros" }] })[0];
    if (f.kind === "line") expect(f.label).toBe("Cuadros");
  });

  it("renders custom text (in text colour) and separators interleaved, in order", () => {
    const rows = previewRows({
      ...DEFAULT_MODEL,
      colors: { ...DEFAULT_MODEL.colors, text: "cccccc" },
      items: [
        { kind: "metric", id: "fps" },
        { kind: "separator", id: "s" },
        { kind: "text", id: "a", text: "Mi PC" },
      ],
    });
    expect(rows.map((r) => r.kind)).toEqual(["line", "separator", "line"]);
    const text = rows[2];
    if (text.kind === "line") {
      expect(text.value).toBe("Mi PC");
      expect(text.valueColor).toBe("#cccccc");
    }
  });

  it("custom text is small unless noSmallFont forces one size", () => {
    const items: HudItem[] = [{ kind: "text", id: "a", text: "x" }];
    const small = previewRows({ ...DEFAULT_MODEL, items })[0];
    const big = previewRows({ ...DEFAULT_MODEL, items, noSmallFont: true })[0];
    if (small.kind === "line") expect(small.small).toBe(true);
    if (big.kind === "line") expect(big.small).toBe(false);
  });

  it("is empty when nothing is selected", () => {
    expect(previewRows({ ...DEFAULT_MODEL, items: [] })).toEqual([]);
  });
});

describe("blocks (GPU/CPU one expandable row each)", () => {
  it("blockGroupOf groups gpu/vram under GPU, cpu under CPU, battery under BATTERY, others null", () => {
    expect(blockGroupOf("gpu")).toBe("gpu");
    expect(blockGroupOf("vram")).toBe("gpu");
    expect(blockGroupOf("cpu_temp")).toBe("cpu");
    expect(blockGroupOf("battery")).toBe("battery");
    expect(blockGroupOf("device_battery")).toBe("battery");
    expect(blockGroupOf("fps")).toBeNull();
    expect(blockGroupOf("ram")).toBeNull();
  });

  it("blockMetricIds lists every sub-metric of a group", () => {
    expect(blockMetricIds("gpu")).toContain("vram");
    expect(blockMetricIds("cpu")).toContain("cores");
    expect(blockMetricIds("battery")).toContain("battery_watt");
  });

  it("listRows collapses a contiguous battery run into one block row", () => {
    const rows = listRows(metrics("fps", "battery", "battery_watt", "ram"));
    expect(rows.map((r) => r.kind)).toEqual(["metric", "block", "metric"]);
    const block = rows[1];
    if (block.kind === "block") {
      expect(block.group).toBe("battery");
      expect(block.ids).toEqual(["battery", "battery_watt"]);
    }
  });

  it("listRows collapses a contiguous GPU run into one block row", () => {
    const rows = listRows(metrics("fps", "gpu", "gpu_temp", "ram"));
    expect(rows.map((r) => r.kind)).toEqual(["metric", "block", "metric"]);
    const block = rows[1];
    if (block.kind === "block") {
      expect(block.group).toBe("gpu");
      expect(block.ids).toEqual(["gpu", "gpu_temp"]);
      expect(block.start).toBe(1);
      expect(block.len).toBe(2);
    }
  });

  it("addMetricItem keeps a block-group metric contiguous with its block", () => {
    // gpu_temp inserted right after the existing gpu run, not appended past fps
    const next = addMetricItem(metrics("gpu", "fps"), "gpu_temp");
    expect(next).toEqual(metrics("gpu", "gpu_temp", "fps"));
  });

  it("addMetricItem appends a standalone metric and is a no-op if present", () => {
    expect(addMetricItem(metrics("fps"), "ram")).toEqual(metrics("fps", "ram"));
    expect(addMetricItem(metrics("fps"), "fps")).toEqual(metrics("fps"));
  });

  it("hasBlock is true when any member metric is present", () => {
    expect(hasBlock(metrics("vram"), "gpu")).toBe(true);
    expect(hasBlock(metrics("fps"), "gpu")).toBe(false);
  });

  it("removeRow drops a whole block, and a single row otherwise", () => {
    const items = metrics("fps", "gpu", "gpu_temp", "ram");
    expect(removeRow(items, 1)).toEqual(metrics("fps", "ram")); // block row
    expect(removeRow(items, 0)).toEqual(metrics("gpu", "gpu_temp", "ram")); // single
  });

  it("moveRow moves a whole block as a unit and clamps at the ends", () => {
    const items = metrics("fps", "gpu", "gpu_temp"); // rows: [fps], [gpu block]
    expect(moveRow(items, 0, 1)).toEqual(metrics("gpu", "gpu_temp", "fps"));
    expect(moveRow(items, 1, 1)).toEqual(items); // clamp
    expect(moveRow(items, 0, -1)).toEqual(items); // clamp
  });
});

describe("item helpers", () => {
  it("toggleMetricItem adds then removes", () => {
    const added = toggleMetricItem(metrics("fps"), "ram");
    expect(added).toEqual(metrics("fps", "ram"));
    expect(toggleMetricItem(added, "fps")).toEqual(metrics("ram"));
  });

  it("addTextItem / addSeparator append the right item", () => {
    expect(addTextItem(metrics("fps"), "x", "hola")[1]).toEqual({ kind: "text", id: "x", text: "hola" });
    expect(addSeparator(metrics("fps"), "s")[1]).toEqual({ kind: "separator", id: "s" });
  });

  it("setMetricLabel sets and clears the label on a labellable metric only", () => {
    const set = setMetricLabel(metrics("fps"), "fps", "Cuadros");
    expect(set[0]).toEqual({ kind: "metric", id: "fps", label: "Cuadros" });
    expect(setMetricLabel(set, "fps", "  ")).toEqual(metrics("fps")); // blank clears
    expect(setMetricLabel(metrics("vram"), "vram", "x")).toEqual(metrics("vram")); // not labellable
  });

  it("setTextAt edits a text item", () => {
    const items: HudItem[] = [{ kind: "text", id: "a", text: "old" }];
    expect(setTextAt(items, 0, "new")[0]).toEqual({ kind: "text", id: "a", text: "new" });
  });
});

describe("canLabel", () => {
  it("is true for fps/cpu/gpu and the pdc metrics, false otherwise", () => {
    expect(canLabel("fps")).toBe(true);
    expect(canLabel("cpu")).toBe(true);
    expect(canLabel("gpu")).toBe(true);
    expect(canLabel("pdc_tdp")).toBe(true);
    expect(canLabel("pdc_power")).toBe(true);
    expect(canLabel("vram")).toBe(false);
    expect(canLabel("battery")).toBe(false);
  });
});

describe("pdc (Panel de Control) metrics", () => {
  it("has a pdc group listing all plugin-state metrics", () => {
    const pdc = GROUPS.find((g) => g.key === "pdc");
    expect(pdc?.ids).toEqual([
      "pdc_tdp", "pdc_tdp_learn", "pdc_auto_tdp", "pdc_fan", "pdc_fan_rpm", "pdc_eco",
      "pdc_profile", "pdc_power", "pdc_charge", "pdc_bat_health", "pdc_smt", "pdc_boost",
      "pdc_cores", "pdc_gpu_clock", "pdc_model",
    ]);
  });
  it("renders a pdc metric as a normal preview line (label + sample value)", () => {
    const rows = previewRows({ ...DEFAULT_MODEL, items: [{ kind: "metric", id: "pdc_tdp" }] });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "line", label: "TDP", value: "Auto 18W" });
  });
});

describe("spacer", () => {
  it("addSpacer appends a spacer with a default small size", () => {
    expect(addSpacer(metrics("fps"), "sp1")[1]).toEqual({ kind: "spacer", id: "sp1", size: "small" });
    expect(addSpacer(metrics("fps"), "sp1", "large")[1]).toEqual({ kind: "spacer", id: "sp1", size: "large" });
  });
  it("setSpacerSizeAt changes the size of a spacer only", () => {
    const items: HudItem[] = [{ kind: "spacer", id: "sp1", size: "small" }];
    expect(setSpacerSizeAt(items, 0, "medium")[0]).toEqual({ kind: "spacer", id: "sp1", size: "medium" });
    // no-op on a non-spacer item
    expect(setSpacerSizeAt(metrics("fps"), 0, "large")).toEqual(metrics("fps"));
  });
  it("listRows keeps a spacer as its own row and previewRows emits a spacer row", () => {
    const items: HudItem[] = [{ kind: "metric", id: "fps" }, { kind: "spacer", id: "sp1", size: "medium" }];
    expect(listRows(items).map((r) => r.kind)).toEqual(["metric", "spacer"]);
    const rows = previewRows({ ...DEFAULT_MODEL, items });
    expect(rows.map((r) => r.kind)).toEqual(["line", "spacer"]);
    const sp = rows[1];
    if (sp.kind === "spacer") expect(sp.size).toBe("medium");
  });
  it("moveRow and removeRow treat a spacer as a single row", () => {
    const items: HudItem[] = [{ kind: "metric", id: "fps" }, { kind: "spacer", id: "sp1", size: "small" }];
    expect(moveRow(items, 1, -1)).toEqual([items[1], items[0]]);
    expect(removeRow(items, 1)).toEqual([items[0]]);
  });
});

describe("colour maths", () => {
  it("rgbToHex pads + clamps each channel", () => {
    expect(rgbToHex({ r: 0, g: 0, b: 0 })).toBe("000000");
    expect(rgbToHex({ r: 255, g: 16, b: 5 })).toBe("ff1005");
    expect(rgbToHex({ r: 300, g: -5, b: 10 })).toBe("ff000a"); // clamped
  });
  it("hexToRgb parses 6- and 3-digit, tolerates '#', black on garbage", () => {
    expect(hexToRgb("#ff1005")).toEqual({ r: 255, g: 16, b: 5 });
    expect(hexToRgb("f00")).toEqual({ r: 255, g: 0, b: 0 });
    expect(hexToRgb("nope")).toEqual({ r: 0, g: 0, b: 0 });
  });
  it("hex round-trips through rgb", () => {
    expect(rgbToHex(hexToRgb("6ee7b7"))).toBe("6ee7b7");
  });
  it("normalizeHex returns clean hex or null", () => {
    expect(normalizeHex("#ABCDEF")).toBe("abcdef");
    expect(normalizeHex("abc")).toBe("aabbcc");
    expect(normalizeHex("12")).toBeNull();
  });
});

describe("catalog + presets + groups", () => {
  it("every metric has a category that exists in the default colors", () => {
    for (const m of METRICS) expect(Object.keys(DEFAULT_MODEL.colors)).toContain(m.category);
  });
  it("presets reference only catalog ids", () => {
    const ids = new Set(METRICS.map((m) => m.id));
    for (const list of Object.values(PRESETS)) for (const id of list) expect(ids.has(id)).toBe(true);
  });
  it("groups cover every catalog metric exactly once", () => {
    const grouped = GROUPS.flatMap((g) => g.ids).sort();
    expect(grouped).toEqual(METRICS.map((m) => m.id).sort());
  });
});
