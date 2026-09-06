import type { CssLoaderPatch } from "./cssLoaderTypes";

export type ThemePatchGroupId = "appearance" | "grid" | "animations" | "performance" | "compatibility";

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
];

const GROUP_MATCHERS: Readonly<Record<Exclude<ThemePatchGroupId, "appearance">, RegExp>> = {
  grid: /grid|parrilla|cover|carátula|caratula|column|row|fila|library|biblioteca|card|tarjeta/,
  animations: /anim|motion|movimiento|transition|transición|transicion|spring|parallax/,
  performance: /performance|rendimiento|quality|calidad|blur|desenfoque|effect|efecto|fps|budget/,
  compatibility: /compat|navigation|navegación|navegacion|fallback|legacy|steam|decky/,
};

function groupForPatch(patch: CssLoaderPatch): ThemePatchGroupId {
  const name = patch.name.toLocaleLowerCase();
  for (const group of GROUP_ORDER.slice(1) as Exclude<ThemePatchGroupId, "appearance">[]) {
    if (GROUP_MATCHERS[group].test(name)) return group;
  }
  return "appearance";
}

export function groupThemePatches(patches: readonly CssLoaderPatch[]): ThemePatchGroup[] {
  const grouped = new Map(GROUP_ORDER.map((id) => [id, [] as CssLoaderPatch[]]));
  for (const patch of patches) grouped.get(groupForPatch(patch))?.push(patch);
  return GROUP_ORDER
    .map((id) => ({ id, patches: grouped.get(id) ?? [] }))
    .filter((group) => group.patches.length > 0);
}
