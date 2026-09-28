import type { CssLoaderTheme } from "./cssLoaderTypes";

export type SectionHandoffs = Readonly<Record<string, string>>;

export interface SectionPatchRef {
  themeName: string;
  patchName: string;
}

const SECTION_PREFIX = "estilizar ";
const HANDOFF_SEPARATOR = "\u0000";
const SECTION_KEYS: readonly (readonly [RegExp, string])[] = [
  [/\binicio\b/, "home"],
  [/\bbiblioteca\b/, "library"],
  [/\bdetalles\b/, "details"],
  [/\bajustes\b/, "settings"],
  [/\bdescargas\b/, "downloads"],
  [/\blogros\b/, "achievements"],
  [/\bnotificaciones\b/, "notifications"],
  [/\bmenus?\b/, "menu"],
  [/\bqam\b/, "qam"],
  [/\bpanel de control\b/, "panel"],
  [/\bmando\b/, "controller"],
];
export const SECTION_ON = "Yes";
export const SECTION_OFF = "No";

export function sectionKeyOf(patchName: string): string | null {
  const normalized = patchName.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  if (!normalized.startsWith(SECTION_PREFIX)) return null;
  const rest = normalized.slice(SECTION_PREFIX.length);
  return SECTION_KEYS.find(([pattern]) => pattern.test(rest))?.[1] ?? null;
}

export function sectionHandoffKey({ themeName, patchName }: SectionPatchRef): string {
  return `${themeName}${HANDOFF_SEPARATOR}${patchName}`;
}

function refOfKey(key: string): SectionPatchRef {
  const [themeName, patchName] = key.split(HANDOFF_SEPARATOR);
  return { themeName, patchName };
}

export function parseSectionHandoffs(raw: string | null): SectionHandoffs {
  if (!raw) return {};
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ));
  } catch {
    return {};
  }
}

function switchable(themes: readonly CssLoaderTheme[], ref: SectionPatchRef, from: string, to: string): boolean {
  const patch = themes.find((theme) => theme.name === ref.themeName)?.patches
    .find((candidate) => candidate.name === ref.patchName);
  return patch?.value === from && patch.options.includes(to);
}

export function planSectionHandoff(
  themes: readonly CssLoaderTheme[],
  ownerName: string,
  hooandeeThemes: ReadonlySet<string>,
  onlyPatchName?: string,
): SectionPatchRef[] {
  const owner = themes.find((theme) => theme.name === ownerName);
  if (!owner?.enabled || !hooandeeThemes.has(ownerName)) return [];
  const owned = new Set(owner.patches
    .filter((patch) => patch.value === SECTION_ON && (onlyPatchName === undefined || patch.name === onlyPatchName))
    .map((patch) => sectionKeyOf(patch.name))
    .filter((key): key is string => key !== null));
  if (owned.size === 0) return [];
  return themes
    .filter((theme) => theme.enabled && theme.name !== ownerName && hooandeeThemes.has(theme.name))
    .flatMap((theme) => theme.patches
      .filter((patch) => {
        const key = sectionKeyOf(patch.name);
        return key !== null && owned.has(key) && patch.value === SECTION_ON && patch.options.includes(SECTION_OFF);
      })
      .map((patch) => ({ themeName: theme.name, patchName: patch.name })));
}

export function planSectionRestore(
  themes: readonly CssLoaderTheme[],
  handoffs: SectionHandoffs,
  leavingOwner: string,
): SectionPatchRef[] {
  return Object.entries(handoffs)
    .filter(([, owner]) => owner === leavingOwner)
    .map(([key]) => refOfKey(key))
    .filter((ref) => switchable(themes, ref, SECTION_OFF, SECTION_ON));
}

export function handoffsGivenBy(handoffs: SectionHandoffs, themeName: string): SectionPatchRef[] {
  return Object.keys(handoffs).map(refOfKey).filter((ref) => ref.themeName === themeName);
}

export function planSectionReclaim(
  themes: readonly CssLoaderTheme[],
  handoffs: SectionHandoffs,
  themeName: string,
): SectionPatchRef[] {
  return handoffsGivenBy(handoffs, themeName).filter((ref) => switchable(themes, ref, SECTION_OFF, SECTION_ON));
}
