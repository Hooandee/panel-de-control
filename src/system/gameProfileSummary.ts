import type { GameProfileRow } from "../api";
import type { SectionId } from "./gameProfiles";

type T = (key: string, params?: Record<string, string | number>) => string;

export interface SectionLine {
  label: string;
  text: string;
  dim: boolean;
}

export function sectionLine(section: SectionId, row: GameProfileRow, t: T): SectionLine | null {
  if (section === "tdp" && row.tdp) {
    if (!row.tdp.auto) {
      return { label: t("gameProfiles.sec.tdp"), text: `${row.tdp.pl1} W`, dim: row.tdp.follows_global };
    }
    const details = [
      t("gameProfiles.auto"),
      `${row.tdp.target_fps} FPS`,
      `${t("tdp.auto.initial.label")} ${row.tdp.initial_tdp} W`,
    ];
    if (row.tdp.min_tdp != null && row.tdp.max_tdp != null) {
      details.push(`${t("tdp.auto.range.title")} ${row.tdp.min_tdp}–${row.tdp.max_tdp} W`);
    } else if (row.tdp.min_tdp != null) {
      details.push(`${t("tdp.auto.range.min")} ${row.tdp.min_tdp} W`);
    } else if (row.tdp.max_tdp != null) {
      details.push(`${t("tdp.auto.range.max")} ${row.tdp.max_tdp} W`);
    }
    return { label: t("gameProfiles.sec.tdp"), text: details.join(" · "), dim: row.tdp.follows_global };
  }
  if (section === "fan" && row.fan) {
    return { label: t("gameProfiles.sec.fan"), text: t(`fans.preset.${row.fan.preset}`), dim: row.fan.follows_global };
  }
  if (section === "color" && row.color) {
    const extra = [row.color.calibrated ? t("gameProfiles.calibrated") : "", row.color.hdr ? "HDR" : ""].filter(Boolean);
    return { label: t("gameProfiles.sec.color"), text: [t("gameProfiles.sat", { v: row.color.saturation }), ...extra].join(" · "), dim: row.color.follows_global };
  }
  if (section === "cpu" && row.cpu) {
    const parts = [
      `SMT ${row.cpu.smt ? "on" : "off"}`,
      `${t("gameProfiles.boost")} ${row.cpu.boost ? "on" : "off"}`,
    ];
    if (row.cpu.cores != null) parts.push(t("gameProfiles.cores", { n: row.cpu.cores }));
    const frequency = row.cpu.frequency;
    if (frequency?.manual && frequency.min_khz != null && frequency.max_khz != null) {
      parts.push(`${(frequency.min_khz / 1_000_000).toFixed(2)}–${(frequency.max_khz / 1_000_000).toFixed(2)} GHz`);
    }
    return { label: t("gameProfiles.sec.cpu"), text: parts.join(" · "), dim: row.cpu.follows_global };
  }
  if (section === "gpu" && row.gpu) {
    const window = row.gpu.manual && row.gpu.min != null && row.gpu.max != null
      ? `${row.gpu.min}–${row.gpu.max} MHz`
      : t("gameProfiles.auto");
    return { label: t("gameProfiles.sec.gpu"), text: window, dim: row.gpu.follows_global };
  }
  if (section === "mandos" && row.mandos) {
    return { label: t("gameProfiles.sec.mandos"), text: t("gameProfiles.buttons", { n: row.mandos.count }), dim: row.mandos.follows_global };
  }
  if (section === "audio" && row.audio) {
    return { label: t("gameProfiles.sec.audio"), text: t("gameProfiles.audioCustom"), dim: row.audio.follows_global };
  }
  return null;
}
