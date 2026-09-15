import type { CssLoaderPatch } from "./cssLoaderTypes";

export type ThemePatchGroupId = "appearance" | "grid" | "animations" | "performance" | "compatibility" | "sections";

export interface ThemePatchGroup {
  id: ThemePatchGroupId;
  patches: CssLoaderPatch[];
}

const GROUP_ORDER: readonly ThemePatchGroupId[] = [
  "appearance",
  "grid",
  "animations",
  "performance",
  "compatibility",
  "sections",
];

const GROUP_MATCHERS: Readonly<Record<Exclude<ThemePatchGroupId, "appearance" | "sections">, RegExp>> = {
  grid: /grid|parrilla|cover|carátula|caratula|column|row|fila|library|biblioteca|card|tarjeta/,
  animations: /anim|motion|movimiento|transition|transición|transicion|spring|parallax/,
  performance: /performance|rendimiento|quality|calidad|blur|desenfoque|effect|efecto|fps|budget/,
  compatibility: /compat|navigation|navegación|navegacion|fallback|legacy|steam|decky/,
};

const GALLERY_SECTION_PATCHES = new Set([
  "Estilizar Inicio",
  "Estilizar Biblioteca y parrilla",
  "Estilizar detalles del juego",
  "Estilizar Ajustes",
  "Estilizar Descargas",
  "Estilizar multimedia y logros",
  "Estilizar menús y barras",
  "Estilizar notificaciones",
]);

function groupForPatch(patch: CssLoaderPatch, themeId?: string): ThemePatchGroupId {
  if (themeId === "hooandee-gallery" && patch.type === "checkbox" && GALLERY_SECTION_PATCHES.has(patch.name)) {
    return "sections";
  }
  const name = patch.name.toLocaleLowerCase();
  for (const group of Object.keys(GROUP_MATCHERS) as Exclude<ThemePatchGroupId, "appearance" | "sections">[]) {
    if (GROUP_MATCHERS[group].test(name)) return group;
  }
  return "appearance";
}

export function groupThemePatches(patches: readonly CssLoaderPatch[], themeId?: string): ThemePatchGroup[] {
  const grouped = new Map(GROUP_ORDER.map((id) => [id, [] as CssLoaderPatch[]]));
  for (const patch of patches) grouped.get(groupForPatch(patch, themeId))?.push(patch);
  return GROUP_ORDER
    .map((id) => ({ id, patches: grouped.get(id) ?? [] }))
    .filter((group) => group.patches.length > 0);
}
