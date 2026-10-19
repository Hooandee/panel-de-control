import { SUPPORTED_LANGUAGES, type Lang } from "../i18n/languages";

type LocalizedLabel = Partial<Record<Lang, string>>;

export type ThemePatchLabelGroup = "extra";

interface PatchLabelEntry {
  name: LocalizedLabel;
  values: Readonly<Record<string, LocalizedLabel>>;
  group?: ThemePatchLabelGroup;
}

export type ThemePatchLabels = Readonly<Record<string, PatchLabelEntry>>;

export interface PatchLabels {
  name: string;
  option(value: string): string;
}

const MAX_LABEL_CHARS = 120;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function localized(value: unknown): LocalizedLabel {
  if (!isRecord(value)) return {};
  const label: LocalizedLabel = {};
  for (const lang of SUPPORTED_LANGUAGES) {
    const text = value[lang];
    if (typeof text === "string" && text.trim() && text.length <= MAX_LABEL_CHARS) label[lang] = text;
  }
  return label;
}

// Translated names a Hooandee theme ships for its CSS Loader options; the internal names remain
// the keys because CSS Loader stores each choice under them.
export function parseThemePatchLabels(value: unknown): ThemePatchLabels {
  if (!isRecord(value)) return {};
  const labels: Record<string, PatchLabelEntry> = {};
  for (const [patch, entry] of Object.entries(value)) {
    if (!isRecord(entry)) continue;
    const values: Record<string, LocalizedLabel> = {};
    if (isRecord(entry.values)) {
      for (const [option, label] of Object.entries(entry.values)) values[option] = localized(label);
    }
    labels[patch] = { name: localized(entry.name), values, ...(entry.group === "extra" ? { group: entry.group } : {}) };
  }
  return labels;
}

function entryFor(labels: ThemePatchLabels, patch: string): PatchLabelEntry | undefined {
  return Object.prototype.hasOwnProperty.call(labels, patch) ? labels[patch] : undefined;
}

export function patchLabelGroup(labels: ThemePatchLabels, patch: string): ThemePatchLabelGroup | undefined {
  return entryFor(labels, patch)?.group;
}

export function labelsForPatch(labels: ThemePatchLabels, patch: string, lang: Lang): PatchLabels {
  const entry = entryFor(labels, patch);
  return {
    name: entry?.name[lang] ?? patch,
    option: (value) => (entry && Object.prototype.hasOwnProperty.call(entry.values, value) ? entry.values[value][lang] : undefined) ?? value,
  };
}
