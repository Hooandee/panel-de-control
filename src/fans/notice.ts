import { FanCurveState } from "../api";

type Translate = (key: string, params?: Record<string, string | number>) => string;

/**
 * The honest note for a device whose fan curve can't be edited: governed by a
 * firmware mode → name it; custom on a firmware-mode device → point to the TDP modes;
 * otherwise the OS-named generic note.
 */
export function fanCurveNotice(cs: FanCurveState, t: Translate): string {
  if (cs.firmware_mode) return t("fans.curve.governed", { mode: t(`tdp.fwmode.${cs.firmware_mode}`) });
  if (cs.has_firmware_modes) return t("fans.curve.custom_mode");
  return t("fans.curve.unsupported", { os: cs.os_name || t("fans.curve.thisSystem") });
}
