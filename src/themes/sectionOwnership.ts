import type { CssLoaderTheme } from "./cssLoaderTypes";

export type SectionHandoffs = Readonly<Record<string, string>>;

export interface SectionPatchRef {
  themeName: string;
  patchName: string;
}

const SECTION_PREFIX = "estilizar ";
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
const ON = "Yes";
const OFF = "No";

export function sectionKeyOf(patchName: string): string | null {
  const normalized = patchName.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  if (!normalized.startsWith(SECTION_PREFIX)) return null;
  const rest = normalized.slice(SECTION_PREFIX.length);
  return SECTION_KEYS.find(([pattern]) => pattern.test(rest))?.[1] ?? null;
}

export function sectionHandoffKey({ themeName, patchName }: SectionPatchRef): string {
  return `${themeName}\u0000${patchName}`;
}

// Two Hooandee themes styling the same Steam section overwrite each other's geometry, so each
// section is styled by one theme at a time; mixing means taking different sections from each.
export function planSectionHandoff(
  themes: readonly CssLoaderTheme[],
  ownerName: string,
  hooandeeThemes: ReadonlySet<string>,
  onlyPatchName?: string,
): SectionPatchRef[] {
  const owner = themes.find((theme) => theme.name === ownerName);
  if (!owner?.enabled || !hooandeeThemes.has(ownerName)) return [];
  const owned = new Set(owner.patches
    .filter((patch) => patch.value === ON && (onlyPatchName === undefined || patch.name === onlyPatchName))
    .map((patch) => sectionKeyOf(patch.name))
    .filter((key): key is string => key !== null));
  if (owned.size === 0) return [];
  return themes
    .filter((theme) => theme.enabled && theme.name !== ownerName && hooandeeThemes.has(theme.name))
    .flatMap((theme) => theme.patches
      .filter((patch) => {
        const key = sectionKeyOf(patch.name);
        return key !== null && owned.has(key) && patch.value === ON && patch.options.includes(OFF);
      })
      .map((patch) => ({ themeName: theme.name, patchName: patch.name })));
}

export function planSectionRestore(
  themes: readonly CssLoaderTheme[],
  handoffs: SectionHandoffs,
  leavingOwner: string,
): SectionPatchRef[] {
  return Object.entries(handoffs).flatMap(([key, owner]) => {
    if (owner !== leavingOwner) return [];
    const [themeName, patchName] = key.split("\u0000");
    const patch = themes.find((theme) => theme.name === themeName)?.patches.find((candidate) => candidate.name === patchName);
    return patch?.value === OFF && patch.options.includes(ON) ? [{ themeName, patchName }] : [];
  });
}
